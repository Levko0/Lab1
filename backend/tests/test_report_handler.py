"""Tests for the reports Lambda handler (app/reports/lambda_handler.py)."""

import json
import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.reports.lambda_handler import handler, previous_iso_week


def test_previous_iso_week_calculation():
    # Tuesday 2026-10-13 is ISO week 2026-W42 -> previous week is 2026-W41
    dt = datetime(2026, 10, 13, 12, 0, 0, tzinfo=ZoneInfo("Europe/Kyiv"))
    assert previous_iso_week(dt) == "2026-W41"

    # Monday 2026-01-05 is week 2026-W02 -> previous week is 2026-W01
    dt_new_year = datetime(2026, 1, 5, 1, 0, 0, tzinfo=ZoneInfo("Europe/Kyiv"))
    assert previous_iso_week(dt_new_year) == "2026-W01"

    # Monday 2026-12-28 is week 2026-W53 -> previous week is 2026-W52
    dt_end_year = datetime(2026, 12, 28, 9, 0, 0, tzinfo=ZoneInfo("Europe/Kyiv"))
    assert previous_iso_week(dt_end_year) == "2026-W52"


@patch("app.reports.lambda_handler.boto3.client")
@patch("app.reports.lambda_handler.build_weekly_report", new_callable=AsyncMock)
def test_direct_invocation(mock_build, mock_boto_client, monkeypatch, caplog):
    monkeypatch.setenv("REPORTS_BUCKET", "test-bucket")
    mock_s3 = MagicMock()
    mock_boto_client.return_value = mock_s3
    mock_build.return_value = b"csv,content\n"

    event = {"week": "2026-W40", "source": "make"}
    with caplog.at_level(logging.INFO):
        res = handler(event, None)

    assert res["status"] == "ok"
    assert res["week"] == "2026-W40"
    assert res["bucket"] == "test-bucket"
    assert res["key"] == "reports/2026-W40.csv"

    mock_build.assert_awaited_once()
    assert mock_build.await_args[0][1] == "2026-W40"

    mock_s3.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="reports/2026-W40.csv",
        Body=b"csv,content\n",
        ContentType="text/csv",
    )

    records = [r for r in caplog.records if r.message == "report-builder triggered"]
    assert len(records) == 1
    rec = records[0]
    assert rec.trigger == "make"
    assert rec.transport == "direct"
    assert rec.week == "2026-W40"


@patch("app.reports.lambda_handler.boto3.client")
@patch("app.reports.lambda_handler.build_weekly_report", new_callable=AsyncMock)
def test_sqs_invocation(mock_build, mock_boto_client, monkeypatch, caplog):
    monkeypatch.setenv("REPORTS_BUCKET", "test-bucket")
    mock_s3 = MagicMock()
    mock_boto_client.return_value = mock_s3
    mock_build.return_value = b"csv,data\n"

    payload = {"week": "2026-W39", "source": "schedule"}
    event = {"Records": [{"body": json.dumps(payload)}]}

    with caplog.at_level(logging.INFO):
        res = handler(event, None)

    assert res["status"] == "ok"
    assert res["week"] == "2026-W39"
    assert res["key"] == "reports/2026-W39.csv"

    mock_build.assert_awaited_once()
    assert mock_build.await_args[0][1] == "2026-W39"

    mock_s3.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="reports/2026-W39.csv",
        Body=b"csv,data\n",
        ContentType="text/csv",
    )

    records = [r for r in caplog.records if r.message == "report-builder triggered"]
    assert len(records) == 1
    rec = records[0]
    assert rec.trigger == "schedule"
    assert rec.transport == "sqs"
    assert rec.week == "2026-W39"


@patch("app.reports.lambda_handler.boto3.client")
@patch("app.reports.lambda_handler.build_weekly_report", new_callable=AsyncMock)
def test_default_previous_week(mock_build, mock_boto_client, monkeypatch, caplog):
    monkeypatch.setenv("REPORTS_BUCKET", "test-bucket")
    mock_s3 = MagicMock()
    mock_boto_client.return_value = mock_s3
    mock_build.return_value = b"csv,data\n"

    expected_week = previous_iso_week()

    # Empty payload defaults week to previous ISO week and source to "direct"
    with caplog.at_level(logging.INFO):
        res = handler({}, None)

    assert res["week"] == expected_week
    assert res["key"] == f"reports/{expected_week}.csv"

    mock_build.assert_awaited_once()
    assert mock_build.await_args[0][1] == expected_week

    records = [r for r in caplog.records if r.message == "report-builder triggered"]
    assert len(records) == 1
    rec = records[0]
    assert rec.trigger == "direct"
    assert rec.transport == "direct"
    assert rec.week == expected_week


@patch("app.reports.lambda_handler.boto3.client")
@patch("app.reports.lambda_handler.build_weekly_report", new_callable=AsyncMock)
def test_error_propagates(mock_build, mock_boto_client, monkeypatch):
    monkeypatch.setenv("REPORTS_BUCKET", "test-bucket")
    mock_build.side_effect = RuntimeError("Database connection failure")

    with pytest.raises(RuntimeError, match="Database connection failure"):
        handler({"week": "2026-W40"}, None)


def test_missing_bucket_raises():
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="REPORTS_BUCKET"):
            handler({"week": "2026-W40"}, None)
