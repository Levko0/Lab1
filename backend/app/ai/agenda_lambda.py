"""AWS Lambda Function URL handler for parsing meeting agendas with Claude Haiku 4.5."""

import asyncio
import base64
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from anthropic import APIStatusError, InternalServerError, RateLimitError
from botocore.exceptions import ClientError

from app.ai.agenda import PROMPT_VERSION, AgendaParseError, parse_agenda
from app.ai.pricing import cost_usd
from app.auth import AuthError, AuthNotConfiguredError, CognitoVerifier, get_verifier
from app.config import settings

MAX_TEXT_LENGTH = 10_000


@lru_cache
def _get_cached_verifier() -> CognitoVerifier:
    return get_verifier()


def _run_async(coro: Any) -> Any:
    """Run an async coroutine safely in both sync and async runtime contexts."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()


def _get_header(headers: dict[str, str], name: str) -> str | None:
    target = name.lower()
    for k, v in headers.items():
        if k.lower() == target:
            return v
    return None


def _response(
    status_code: int, body_data: Any, extra_headers: dict[str, str] | None = None
) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    body = json.dumps(body_data) if not isinstance(body_data, str) else body_data
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": body,
    }


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda entry point for agenda-parser function URL."""
    http_info = event.get("requestContext", {}).get("http", {})
    method = (http_info.get("method") or event.get("httpMethod") or "POST").upper()

    # Handle CORS preflight if reached
    if method == "OPTIONS":
        return _response(
            204,
            "",
            {
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Authorization, Content-Type",
            },
        )

    if method != "POST":
        return _response(405, {"detail": f"Method {method} not allowed. Use POST."})

    headers = event.get("headers") or {}
    auth_header = _get_header(headers, "authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return _response(401, {"detail": "Missing or invalid authorization header."})

    token = auth_header[7:].strip()
    if not token:
        return _response(401, {"detail": "Empty bearer token."})

    try:
        verifier = _get_cached_verifier()
        user = _run_async(verifier.verify(token))
    except (AuthError, AuthNotConfiguredError, Exception) as exc:
        return _response(401, {"detail": f"Unauthorized: {exc}"})

    raw_body = event.get("body")
    if raw_body is None:
        return _response(400, {"detail": "Missing request body."})

    if event.get("isBase64Encoded"):
        try:
            raw_body = base64.b64decode(raw_body).decode("utf-8")
        except Exception:
            return _response(400, {"detail": "Invalid base64 encoding in body."})

    try:
        body_data = json.loads(raw_body)
    except json.JSONDecodeError:
        return _response(400, {"detail": "Request body must be valid JSON."})

    if not isinstance(body_data, dict):
        return _response(400, {"detail": "Request body must be a JSON object."})

    text = body_data.get("text")
    if text is None or not isinstance(text, str):
        return _response(400, {"detail": "Field 'text' is required and must be a string."})

    # 413 check BEFORE calling the model
    if len(text) > MAX_TEXT_LENGTH:
        return _response(
            413,
            {"detail": f"Text exceeds maximum length of {MAX_TEXT_LENGTH:,} characters."},
        )

    today = date.today()
    if "today" in body_data and body_data["today"]:
        try:
            today = date.fromisoformat(body_data["today"])
        except ValueError:
            return _response(400, {"detail": "Invalid 'today' format. Expected YYYY-MM-DD."})

    tz_str = body_data.get("tz") or settings.app_timezone
    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        return _response(400, {"detail": f"Invalid timezone: {tz_str}."})

    start_time = time.perf_counter()
    try:
        agenda, usage = parse_agenda(text=text, today=today, tz=tz)
    except AgendaParseError as exc:
        return _response(422, {"detail": str(exc)})
    except RateLimitError:
        return _response(
            429, {"detail": "Bedrock rate limit exceeded. Please retry in a few moments."}
        )
    except InternalServerError:
        return _response(
            503, {"detail": "Bedrock service temporarily unavailable. Please retry later."}
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("ThrottlingException", "TooManyRequestsException"):
            return _response(429, {"detail": "Bedrock is busy. Please retry in a few moments."})
        if code in ("ModelNotReadyException", "ServiceUnavailableException"):
            return _response(503, {"detail": "Bedrock service is not ready. Please retry later."})
        return _response(500, {"detail": f"Bedrock invocation error: {code}"})
    except APIStatusError as exc:
        if exc.status_code == 429:
            return _response(429, {"detail": "Bedrock rate limit exceeded. Please retry later."})
        if exc.status_code >= 500:
            return _response(503, {"detail": "Bedrock service unavailable. Please retry later."})
        return _response(500, {"detail": f"Bedrock API error: {exc.message}"})
    except Exception as exc:
        return _response(500, {"detail": f"Internal parser error: {exc}"})

    latency_ms = int((time.perf_counter() - start_time) * 1000)
    calc_cost = cost_usd(settings.parser_model, usage)

    # Exactly one structured JSON line for CloudWatch
    log_payload = {
        "event": "agenda_parsed",
        "user": user.sub,
        "model": settings.parser_model,
        "prompt_version": PROMPT_VERSION,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "latency_ms": latency_ms,
        "cost_usd": round(calc_cost, 6),
    }
    print(json.dumps(log_payload), flush=True)

    return _response(
        200,
        {
            "agenda": agenda.model_dump(mode="json"),
            "model": settings.parser_model,
            "prompt_version": PROMPT_VERSION,
        },
    )
