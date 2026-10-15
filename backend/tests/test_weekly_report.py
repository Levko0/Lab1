"""Tests for the weekly CSV report builder (app/reports/weekly.py)."""

import csv
import io
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meeting import Meeting, Participant
from app.reports.weekly import build_weekly_report, report_key


def _parse_report(csv_bytes: bytes) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    """Parse report CSV into summary metrics and top 5 meeting rows."""
    reader = csv.reader(io.StringIO(csv_bytes.decode("utf-8")))
    summary: dict[str, dict[str, str]] = {}
    top5: list[dict[str, str]] = []

    in_summary = True
    summary_header = None
    top5_header = None

    for row in reader:
        if not row:
            in_summary = False
            continue
        if in_summary:
            if summary_header is None:
                summary_header = row
            else:
                metric, this_week, prev_week, change = row
                summary[metric] = {
                    "this_week": this_week,
                    "prev_week": prev_week,
                    "change": change,
                }
        else:
            if top5_header is None:
                top5_header = row
            else:
                top5.append(dict(zip(top5_header, row)))

    return summary, top5


async def _seed_meeting(session: AsyncSession, **kwargs) -> Meeting:
    participants = kwargs.pop("participants", [])
    meeting = Meeting(**kwargs)
    meeting.participants = [
        Participant(name=name, position=i) for i, name in enumerate(participants)
    ]
    session.add(meeting)
    await session.commit()
    return meeting


def test_report_key():
    assert report_key("2026-W40") == "reports/2026-W40.csv"


async def test_invalid_week_string(session: AsyncSession):
    for bad in ["2026-40", "26-W40", "2026-W00", "2026-W54", "2026-W", ""]:
        with pytest.raises(ValueError):
            await build_weekly_report(session, bad)
        with pytest.raises(ValueError):
            report_key(bad)


async def test_empty_week(session: AsyncSession):
    csv_bytes = await build_weekly_report(session, "2026-W40")
    summary, top5 = _parse_report(csv_bytes)

    assert summary["meetings_count"] == {"this_week": "0", "prev_week": "0", "change": "0"}
    assert float(summary["total_duration_hours"]["this_week"]) == 0.0
    assert float(summary["total_duration_hours"]["prev_week"]) == 0.0
    assert float(summary["total_duration_hours"]["change"]) == 0.0
    assert top5 == []


async def test_meetings_inside_week(session: AsyncSession):
    # W40 in Europe/Kyiv: 2026-09-28 00:00 to 2026-10-05 00:00
    await _seed_meeting(
        session,
        name="Review",
        starts_at=datetime.fromisoformat("2026-09-28T10:00:00+03:00"),
        ends_at=datetime.fromisoformat("2026-09-28T11:30:00+03:00"),  # 1.5h
        participants=["Alice", "Bob"],
    )
    await _seed_meeting(
        session,
        name="Planning",
        starts_at=datetime.fromisoformat("2026-09-29T14:00:00+03:00"),
        ends_at=datetime.fromisoformat("2026-09-29T16:00:00+03:00"),  # 2.0h
        participants=["Charlie"],
    )
    # W39 in Europe/Kyiv: 2026-09-21 00:00 to 2026-09-28 00:00
    await _seed_meeting(
        session,
        name="Previous sync",
        starts_at=datetime.fromisoformat("2026-09-22T09:00:00+03:00"),
        ends_at=datetime.fromisoformat("2026-09-22T10:00:00+03:00"),  # 1.0h
    )

    csv_bytes = await build_weekly_report(session, "2026-W40")
    summary, top5 = _parse_report(csv_bytes)

    assert summary["meetings_count"]["this_week"] == "2"
    assert summary["meetings_count"]["prev_week"] == "1"
    assert summary["meetings_count"]["change"] == "1"

    assert float(summary["total_duration_hours"]["this_week"]) == pytest.approx(3.5)
    assert float(summary["total_duration_hours"]["prev_week"]) == pytest.approx(1.0)
    assert float(summary["total_duration_hours"]["change"]) == pytest.approx(2.5)


async def test_boundary_spanning_meeting(session: AsyncSession):
    # Crosses boundary between W39 and W40 (starts Sunday night, ends Monday morning)
    await _seed_meeting(
        session,
        name="Midnight bridge",
        starts_at=datetime.fromisoformat("2026-09-27T23:00:00+03:00"),
        ends_at=datetime.fromisoformat("2026-09-28T01:00:00+03:00"),  # 2.0h
    )

    csv_bytes = await build_weekly_report(session, "2026-W40")
    summary, top5 = _parse_report(csv_bytes)

    # Overlaps both weeks, full duration counted in each week
    assert summary["meetings_count"]["this_week"] == "1"
    assert summary["meetings_count"]["prev_week"] == "1"
    assert summary["meetings_count"]["change"] == "0"

    assert float(summary["total_duration_hours"]["this_week"]) == pytest.approx(2.0)
    assert float(summary["total_duration_hours"]["prev_week"]) == pytest.approx(2.0)
    assert float(summary["total_duration_hours"]["change"]) == pytest.approx(0.0)


async def test_top_5_order(session: AsyncSession):
    durations = [1.0, 6.0, 2.0, 5.0, 3.0, 4.0]
    base_start = datetime.fromisoformat("2026-09-28T08:00:00+03:00")
    for i, duration in enumerate(durations):
        start = base_start + timedelta(days=i)
        await _seed_meeting(
            session,
            name=f"Meeting {duration}h",
            starts_at=start,
            ends_at=start + timedelta(hours=duration),
        )

    csv_bytes = await build_weekly_report(session, "2026-W40")
    _, top5 = _parse_report(csv_bytes)

    assert len(top5) == 5
    top5_hours = [float(row["duration_hours"]) for row in top5]
    assert top5_hours == [6.0, 5.0, 4.0, 3.0, 2.0]
    assert "Meeting 1.0h" not in [row["name"] for row in top5]


async def test_participant_count(session: AsyncSession):
    await _seed_meeting(
        session,
        name="All Hands",
        starts_at=datetime.fromisoformat("2026-09-28T10:00:00+03:00"),
        ends_at=datetime.fromisoformat("2026-09-28T11:00:00+03:00"),
        participants=["Alice", "Bob", "Charlie", "Diana"],
    )

    csv_bytes = await build_weekly_report(session, "2026-W40")
    _, top5 = _parse_report(csv_bytes)

    assert len(top5) == 1
    assert top5[0]["name"] == "All Hands"
    assert top5[0]["participants"] == "4"
