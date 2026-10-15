"""AWS Lambda entry point for scheduled and on-demand weekly reports."""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta

import boto3
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.reports.weekly import build_weekly_report, report_key

log = logging.getLogger("meetings.reports")


class ExtraLogFormatter(logging.Formatter):
    """Formats log records including extra fields (trigger, transport, week)."""

    def format(self, record: logging.LogRecord) -> str:
        transport = getattr(record, "transport", None)
        trigger = getattr(record, "trigger", None)
        week = getattr(record, "week", None)
        extras = []
        if transport == "sqs":
            extras.append("trigger=sqs")
        elif trigger:
            extras.append(f"trigger={trigger}")
        if transport:
            extras.append(f"transport={transport}")
        if week:
            extras.append(f"week={week}")
        base = super().format(record)
        if extras and not any(f"{k}=" in base for k in ("trigger", "transport", "week")):
            return f"{base} [{', '.join(extras)}]"
        return base


def _configure_logging() -> None:
    log.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    if not log.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(ExtraLogFormatter("%(levelname)s %(name)s: %(message)s"))
        log.addHandler(handler)
    else:
        for handler in log.handlers:
            handler.setFormatter(ExtraLogFormatter("%(levelname)s %(name)s: %(message)s"))


_configure_logging()


def previous_iso_week(now: datetime | None = None) -> str:
    """Compute the previous ISO week formatted as 'YYYY-Www' in APP_TIMEZONE."""
    if now is None:
        now = datetime.now(settings.tz)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=settings.tz)
    prev = now - timedelta(days=7)
    iso_year, iso_week, _ = prev.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}"


def _extract_payload_and_transport(event: dict | None) -> tuple[dict, str]:
    """Parse direct invocation or SQS event shape."""
    if not event:
        return {}, "direct"
    if isinstance(event, dict) and "Records" in event and event["Records"]:
        record = event["Records"][0]
        body = record.get("body", {}) if isinstance(record, dict) else {}
        if isinstance(body, str):
            payload = json.loads(body) if body else {}
        elif isinstance(body, dict):
            payload = body
        else:
            payload = {}
        return payload if isinstance(payload, dict) else {}, "sqs"
    return event if isinstance(event, dict) else {}, "direct"


async def _generate_report(database_url: str, week: str) -> bytes:
    """Run weekly report with a fresh NullPool engine disposed on exit."""
    engine = create_async_engine(database_url, echo=False, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        async with session_factory() as session:
            return await build_weekly_report(session, week)
    finally:
        await engine.dispose()


def handler(event, context):
    """Lambda entry point for building and uploading the weekly report."""
    payload, transport = _extract_payload_and_transport(event)
    trigger = payload.get("source") or "direct"

    week = payload.get("week")
    if not week:
        week = previous_iso_week()

    # Log at the start before any work
    log.info(
        "report-builder triggered",
        extra={"trigger": trigger, "transport": transport, "week": week},
    )

    bucket = os.environ.get("REPORTS_BUCKET")
    if not bucket:
        raise ValueError("REPORTS_BUCKET environment variable is not set")

    csv_bytes = asyncio.run(_generate_report(settings.database_url, week))

    s3 = boto3.client("s3")
    key = report_key(week)
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=csv_bytes,
        ContentType="text/csv",
    )

    return {"status": "ok", "bucket": bucket, "key": key, "week": week}
