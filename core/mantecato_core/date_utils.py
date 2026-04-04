from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

DateRangePreset = str
Granularity = str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _start_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _end_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=23, minute=59, second=59, microsecond=999999)


def _start_of_week(dt: datetime) -> datetime:
    d = _start_of_day(dt)
    d = d - timedelta(days=d.weekday())
    return d


def _end_of_week(dt: datetime) -> datetime:
    s = _start_of_week(dt)
    return s + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)


def _start_of_month(dt: datetime) -> datetime:
    return _start_of_day(dt.replace(day=1))


def _end_of_month(dt: datetime) -> datetime:
    if dt.month == 12:
        next_month = dt.replace(year=dt.year + 1, month=1, day=1)
    else:
        next_month = dt.replace(month=dt.month + 1, day=1)
    return _end_of_day(next_month - timedelta(days=1))


def _start_of_quarter(dt: datetime) -> datetime:
    quarter_start_month = ((dt.month - 1) // 3) * 3 + 1
    return _start_of_day(dt.replace(month=quarter_start_month, day=1))


def _end_of_quarter(dt: datetime) -> datetime:
    quarter_start_month = ((dt.month - 1) // 3) * 3 + 1
    quarter_end_month = quarter_start_month + 2
    if quarter_end_month > 12:
        qe = dt.replace(year=dt.year + 1, month=quarter_end_month - 12, day=1)
    else:
        qe = dt.replace(month=quarter_end_month, day=1)
    return _end_of_day(qe - timedelta(days=1))


def _start_of_year(dt: datetime) -> datetime:
    return _start_of_day(dt.replace(month=1, day=1))


def _end_of_year(dt: datetime) -> datetime:
    return _end_of_day(dt.replace(month=12, day=31))


class DateRange:
    def __init__(self, start_date: datetime, end_date: datetime):
        self.start_date = start_date
        self.end_date = end_date


def resolve_date_range(preset: DateRangePreset) -> DateRange | None:
    now = _now()

    if preset == "1h":
        return DateRange(now - timedelta(hours=1), now)
    elif preset == "3h":
        return DateRange(now - timedelta(hours=3), now)
    elif preset == "6h":
        return DateRange(now - timedelta(hours=6), now)
    elif preset == "today":
        return DateRange(_start_of_day(now), now)
    elif preset == "yesterday":
        y = now - timedelta(days=1)
        return DateRange(_start_of_day(y), _end_of_day(y))
    elif preset == "24h":
        return DateRange(now - timedelta(hours=24), now)
    elif preset == "7d":
        return DateRange(now - timedelta(days=7), now)
    elif preset == "14d":
        return DateRange(now - timedelta(days=14), now)
    elif preset == "30d":
        return DateRange(now - timedelta(days=30), now)
    elif preset == "60d":
        return DateRange(now - timedelta(days=60), now)
    elif preset == "90d":
        return DateRange(now - timedelta(days=90), now)
    elif preset == "6m":
        return DateRange(now - timedelta(days=180), now)
    elif preset == "12m":
        return DateRange(now - timedelta(days=365), now)
    elif preset == "this_week":
        return DateRange(_start_of_week(now), now)
    elif preset == "last_week":
        lw = _start_of_week(now) - timedelta(weeks=1)
        return DateRange(lw, _end_of_week(lw))
    elif preset == "this_month":
        return DateRange(_start_of_month(now), now)
    elif preset == "last_month":
        lm = _start_of_month(now) - timedelta(days=1)
        lm = _start_of_month(lm)
        return DateRange(lm, _end_of_month(lm))
    elif preset == "this_quarter":
        return DateRange(_start_of_quarter(now), now)
    elif preset == "last_quarter":
        lq = _start_of_quarter(now) - timedelta(days=1)
        lq = _start_of_quarter(lq)
        return DateRange(lq, _end_of_quarter(lq))
    elif preset == "this_year":
        return DateRange(_start_of_year(now), now)
    elif preset == "last_year":
        ly = now.replace(year=now.year - 1)
        return DateRange(_start_of_year(ly), _end_of_year(ly))
    elif preset in ("all", "custom"):
        return None
    return None


def get_comparison_range(
    range_: DateRange,
    mode: Literal["previous_period", "previous_year"],
) -> DateRange:
    if mode == "previous_year":
        return DateRange(
            range_.start_date.replace(year=range_.start_date.year - 1),
            range_.end_date.replace(year=range_.end_date.year - 1),
        )

    diff = range_.end_date - range_.start_date
    hours = diff.total_seconds() / 3600
    days = diff.total_seconds() / 86400

    if hours < 24:
        return DateRange(
            range_.start_date - timedelta(hours=hours),
            range_.end_date - timedelta(hours=hours),
        )

    d = int(days)
    return DateRange(
        range_.start_date - timedelta(days=d + 1),
        range_.start_date - timedelta(days=1),
    )


def get_auto_granularity(range_: DateRange) -> str:
    diff = range_.end_date - range_.start_date
    hours = diff.total_seconds() / 3600
    days = diff.total_seconds() / 86400

    if hours <= 6:
        return "minute"
    if days <= 1:
        return "hour"
    if days <= 90:
        return "day"
    if days <= 365:
        return "week"
    return "month"


def resolve_granularity(granularity: Granularity, range_: DateRange) -> str:
    if granularity == "auto":
        return get_auto_granularity(range_)
    return granularity
