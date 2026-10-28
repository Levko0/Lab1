import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic import RateLimitError
from anthropic.types import Usage
from botocore.exceptions import ClientError

from app.ai.agenda import AgendaParseError, ParsedAgenda
from app.ai.agenda_lambda import handler
from app.auth import AuthError, CurrentUser


@pytest.fixture
def mock_verifier():
    verifier = MagicMock()
    user = CurrentUser(sub="user-12345", username="lev")
    verifier.verify = AsyncMock(return_value=user)
    return verifier


def _make_event(
    body: dict | str | None = None,
    headers: dict | None = None,
    method: str = "POST",
) -> dict:
    req_headers = {"Authorization": "Bearer valid-token", "Content-Type": "application/json"}
    if headers is not None:
        req_headers = headers

    raw_body = json.dumps(body) if isinstance(body, dict) else body
    return {
        "requestContext": {"http": {"method": method}},
        "headers": req_headers,
        "body": raw_body,
        "isBase64Encoded": False,
    }


def test_options_request():
    event = _make_event(method="OPTIONS")
    res = handler(event)
    assert res["statusCode"] == 204
    assert "Access-Control-Allow-Methods" in res["headers"]


def test_missing_authorization():
    event = _make_event(headers={})
    res = handler(event)
    assert res["statusCode"] == 401
    body = json.loads(res["body"])
    assert "authorization" in body["detail"].lower()


def test_invalid_token(mock_verifier):
    mock_verifier.verify = AsyncMock(side_effect=AuthError("Token is expired."))
    with patch("app.ai.agenda_lambda._get_cached_verifier", return_value=mock_verifier):
        event = _make_event(body={"text": "Hello"})
        res = handler(event)
        assert res["statusCode"] == 401
        assert "Unauthorized" in res["body"]


def test_text_too_long_returns_413(mock_verifier):
    with patch("app.ai.agenda_lambda._get_cached_verifier", return_value=mock_verifier):
        with patch("app.ai.agenda_lambda.parse_agenda") as mock_parse:
            long_text = "A" * 10_001
            event = _make_event(body={"text": long_text})
            res = handler(event)
            assert res["statusCode"] == 413
            body = json.loads(res["body"])
            assert "10,000" in body["detail"]
            # Model MUST NOT be called
            mock_parse.assert_not_called()


def test_missing_or_invalid_body(mock_verifier):
    with patch("app.ai.agenda_lambda._get_cached_verifier", return_value=mock_verifier):
        # Missing body
        res1 = handler(
            {
                "requestContext": {"http": {"method": "POST"}},
                "headers": {"Authorization": "Bearer token"},
            }
        )
        assert res1["statusCode"] == 400

        # Invalid JSON
        res2 = handler(_make_event(body="not a json"))
        assert res2["statusCode"] == 400

        # Missing 'text' key
        res3 = handler(_make_event(body={"other": 123}))
        assert res3["statusCode"] == 400


def test_successful_parse(mock_verifier, capsys):
    parsed = ParsedAgenda(
        title="Sync",
        starts_at="2026-10-27T10:00:00+02:00",
        duration_minutes=30,
        items=[],
        action_items=[],
        language="uk",
    )
    usage = Usage(input_tokens=200, output_tokens=100)

    with patch("app.ai.agenda_lambda._get_cached_verifier", return_value=mock_verifier):
        with patch("app.ai.agenda_lambda.parse_agenda", return_value=(parsed, usage)):
            event = _make_event(
                body={"text": "Короткий синк 30 хв", "today": "2026-10-27", "tz": "Europe/Kyiv"}
            )
            res = handler(event)
            assert res["statusCode"] == 200
            data = json.loads(res["body"])
            assert data["agenda"]["title"] == "Sync"
            assert data["agenda"]["duration_minutes"] == 30
            assert data["prompt_version"] == "agenda-v1"
            assert "model" in data

            # Verify exactly one JSON log line was printed
            captured = capsys.readouterr()
            lines = [ln for ln in captured.out.strip().split("\n") if ln.strip()]
            assert len(lines) == 1
            log_obj = json.loads(lines[0])
            assert log_obj["event"] == "agenda_parsed"
            assert log_obj["user"] == "user-12345"
            assert log_obj["input_tokens"] == 200
            assert log_obj["output_tokens"] == 100
            assert "latency_ms" in log_obj
            assert "cost_usd" in log_obj


def test_agenda_parse_error_returns_422(mock_verifier):
    with patch("app.ai.agenda_lambda._get_cached_verifier", return_value=mock_verifier):
        with patch(
            "app.ai.agenda_lambda.parse_agenda", side_effect=AgendaParseError("Tool call failed")
        ):
            event = _make_event(body={"text": "Неструктурований текст"})
            res = handler(event)
            assert res["statusCode"] == 422
            body = json.loads(res["body"])
            assert "Tool call failed" in body["detail"]


def test_bedrock_rate_limit_returns_429(mock_verifier):
    dummy_resp = MagicMock()
    dummy_resp.status_code = 429
    dummy_resp.headers = {}
    rate_err = RateLimitError("Rate limit", response=dummy_resp, body={})

    with patch("app.ai.agenda_lambda._get_cached_verifier", return_value=mock_verifier):
        with patch("app.ai.agenda_lambda.parse_agenda", side_effect=rate_err):
            event = _make_event(body={"text": "Текст"})
            res = handler(event)
            assert res["statusCode"] == 429
            assert "rate limit" in res["body"].lower()


def test_bedrock_throttling_client_error_returns_429(mock_verifier):
    client_err = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
        "InvokeModel",
    )
    with patch("app.ai.agenda_lambda._get_cached_verifier", return_value=mock_verifier):
        with patch("app.ai.agenda_lambda.parse_agenda", side_effect=client_err):
            event = _make_event(body={"text": "Текст"})
            res = handler(event)
            assert res["statusCode"] == 429
            assert "busy" in res["body"].lower()
