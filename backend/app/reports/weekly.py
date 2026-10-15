"""Weekly CSV report builder.

Public API
----------
report_key(week)              -> "reports/2026-W40.csv"
build_weekly_report(session, week) -> bytes  (UTF-8 CSV)

Week string format: "YYYY-Www"  (e.g. "2026-W40").
Raises ValueError for anything that does not match that pattern.

Overlap rule (same as the list endpoint)
-----------------------------------------
A meeting is counted in a week when:
    starts_at < week_end  AND  ends_at > week_start
where week_start is Monday 00:00 and week_end is the following Monday 00:00,
both in APP_TIMEZONE.

Duration counting
-----------------
When a meeting spans a week boundary its *full* duration (ends_at - starts_at)
is counted in the week it overlaps — consistent with how the list endpoint
counts meetings that cross midnight: the meeting belongs to the day/week it
overlaps, and the full duration is the simplest well-defined metric.
"""

import csv
import io
import re
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.meeting import Meeting, Participant

# "2026-W40" → year=2026, week=40
_WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")


def report_key(week: str) -> str:
    """Return the canonical S3/storage key for a week's report.

    >>> report_key("2026-W40")
    'reports/2026-W40.csv'
    """
    _parse_week(week)          # validate before building the key
    return f"reports/{week}.csv"


def _parse_week(week: str) -> tuple[datetime, datetime]:
    """Parse *week* ("YYYY-Www") and return (week_start, week_end) tz-aware.

    week_start is Monday 00:00 in APP_TIMEZONE.
    week_end   is the following Monday 00:00 in APP_TIMEZONE.

    Raises ValueError for invalid input.
    """
    m = _WEEK_RE.match(week)
    if not m:
        raise ValueError(
            f"Invalid week string {week!r}: expected 'YYYY-Www' (e.g. '2026-W40')."
        )
    year, week_num = int(m.group(1)), int(m.group(2))
    if not (1 <= week_num <= 53):
        raise ValueError(
            f"Invalid week number {week_num} in {week!r}: must be between 01 and 53."
        )
    tz = settings.tz
    # ISO week: Monday of week_num. %G-%V-%u = ISO year-week-weekday.
    monday = datetime.strptime(f"{year}-W{week_num:02d}-1", "%G-W%V-%u")
    week_start = monday.replace(tzinfo=tz)
    week_end = week_start + timedelta(weeks=1)
    return week_start, week_end


async def _week_stats(
    session: AsyncSession,
    week_start: datetime,
    week_end: datetime,
) -> tuple[int, float, list[dict]]:
    """Return (count, total_duration_hours, top5_longest) for the given window.

    Overlap filter: starts_at < week_end AND ends_at > week_start
    (identical to MeetingRepository._overlap_filters).

    Duration note: full meeting duration is used even when the meeting crosses
    the week boundary — consistent with the list endpoint which counts the whole
    meeting inside the day/week it overlaps.
    """
    overlap = (Meeting.starts_at < week_end, Meeting.ends_at > week_start)

    # ── summary (count + total seconds) ──────────────────────────────────────
    # Extract epoch seconds for each boundary and sum the differences.
    duration_expr = func.sum(
        func.extract("epoch", Meeting.ends_at)
        - func.extract("epoch", Meeting.starts_at)
    )
    row = await session.execute(
        select(func.count(Meeting.id), duration_expr).where(*overlap)
    )
    count, total_seconds = row.one()
    count = count or 0
    total_hours = round(float(total_seconds or 0) / 3600, 4)

    # ── top-5 longest ─────────────────────────────────────────────────────────
    # Use a subquery so we can order by duration without repeating the expression.
    dur_expr = (
        func.extract("epoch", Meeting.ends_at)
        - func.extract("epoch", Meeting.starts_at)
    ).label("dur_seconds")

    rows = await session.execute(
        select(Meeting, dur_expr)
        .where(*overlap)
        .order_by(dur_expr.desc(), Meeting.starts_at.asc())
        .limit(5)
    )

    top5 = []
    for meeting, dur_seconds in rows:
        participant_count = len(meeting.participants)
        top5.append(
            {
                "name": meeting.name,
                "starts_at": meeting.starts_at.isoformat(),
                "duration_hours": round(float(dur_seconds or 0) / 3600, 4),
                "participants": participant_count,
            }
        )

    return count, total_hours, top5


async def build_weekly_report(session: AsyncSession, week: str) -> bytes:
    """Build and return a UTF-8 CSV report for *week* ("YYYY-Www").

    CSV layout
    ----------
    Section 1 – summary (one row per metric):

        metric,this_week,prev_week,change
        meetings_count,5,3,2
        total_duration_hours,8.5,4.0,4.5

    Section 2 – top-5 longest meetings (blank line separator):

        name,starts_at,duration_hours,participants
        ...

    Raises ValueError for an invalid week string.
    """
    week_start, week_end = _parse_week(week)
    prev_start = week_start - timedelta(weeks=1)
    prev_end = week_end - timedelta(weeks=1)

    count_cur, hours_cur, top5 = await _week_stats(session, week_start, week_end)
    count_prev, hours_prev, _ = await _week_stats(session, prev_start, prev_end)

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")

    # ── summary section ───────────────────────────────────────────────────────
    writer.writerow(["metric", "this_week", "prev_week", "change"])
    writer.writerow(
        [
            "meetings_count",
            count_cur,
            count_prev,
            count_cur - count_prev,
        ]
    )
    writer.writerow(
        [
            "total_duration_hours",
            hours_cur,
            hours_prev,
            round(hours_cur - hours_prev, 4),
        ]
    )

    # ── top-5 section ─────────────────────────────────────────────────────────
    writer.writerow([])  # blank separator line
    writer.writerow(["name", "starts_at", "duration_hours", "participants"])
    for m in top5:
        writer.writerow(
            [m["name"], m["starts_at"], m["duration_hours"], m["participants"]]
        )

    return buf.getvalue().encode("utf-8")
