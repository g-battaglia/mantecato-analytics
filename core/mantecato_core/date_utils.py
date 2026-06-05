"""Date range resolution and granularity helpers.

Ported identically from mantecato-core legacy — no async dependencies.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

DateRangePreset = str
Granularity = str


def _now() -> datetime:
    """Return the current moment in UTC.

    This is the single source of truth for "now" throughout the date range
    resolution engine. All preset calculations (``"today"``, ``"7d"``,
    ``"this_month"``, etc.) anchor to the value returned here.

    Centralising the call makes the module deterministic in tests: stub
    ``_now`` to freeze time without touching ``datetime.now`` globally.

    Returns:
        A timezone-aware ``datetime`` pinned to ``datetime.UTC``.
    """
    return datetime.now(UTC)


def _start_of_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def _end_of_hour(dt: datetime) -> datetime:
    return dt.replace(minute=59, second=59, microsecond=999999)


def _start_of_day(dt: datetime) -> datetime:
    """Return *dt* floored to midnight (00:00:00.000000) of the same day.

    The timezone info of *dt* is preserved; only the time components are
    zeroed out.  This is the foundation for every "start of ..." helper --
    ``_start_of_week``, ``_start_of_month``, etc. -- which first derive the
    correct date and then delegate here to clear the time portion.

    Args:
        dt: A datetime (timezone-aware or naive) to floor.

    Returns:
        A new ``datetime`` with ``hour=0, minute=0, second=0, microsecond=0``
        and the same date and ``tzinfo`` as *dt*.
    """
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _end_of_day(dt: datetime) -> datetime:
    """Return *dt* ceiled to the last microsecond of the same day (23:59:59.999999).

    This is the inclusive upper-bound counterpart of ``_start_of_day``.
    Because PostgreSQL ``BETWEEN`` is inclusive on both sides, the
    ``microsecond=999999`` ensures the entire day is captured without
    bleeding into the next day.

    Args:
        dt: A datetime (timezone-aware or naive) to ceil.

    Returns:
        A new ``datetime`` set to 23:59:59.999999 on the same date, with
        the original ``tzinfo`` preserved.
    """
    return dt.replace(hour=23, minute=59, second=59, microsecond=999999)


def _start_of_week(dt: datetime) -> datetime:
    """Return midnight of the Monday in the ISO week containing *dt*.

    The ISO week starts on Monday (``weekday() == 0``).  The function
    subtracts ``dt.weekday()`` days to rewind to Monday and then floors
    the time component via ``_start_of_day``.

    Args:
        dt: Any datetime within the target week.

    Returns:
        Midnight (00:00:00.000000) on the Monday of the ISO week that
        contains *dt*, preserving the original ``tzinfo``.
    """
    d = _start_of_day(dt)
    # weekday() returns 0 for Monday, so subtracting it rewinds to Monday.
    d = d - timedelta(days=d.weekday())
    return d


def _end_of_week(dt: datetime) -> datetime:
    """Return the last microsecond of the Sunday in the ISO week containing *dt*.

    Starts from ``_start_of_week`` (Monday 00:00) and adds 6 days plus
    23:59:59.999999 to land on Sunday 23:59:59.999999.  This forms the
    inclusive upper bound for a full ISO-week query.

    Args:
        dt: Any datetime within the target week.

    Returns:
        Sunday 23:59:59.999999 of the same ISO week, preserving ``tzinfo``.
    """
    s = _start_of_week(dt)
    return s + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)


def _start_of_month(dt: datetime) -> datetime:
    """Return midnight on the first day of the month containing *dt*.

    Simply replaces ``day`` with 1 and delegates to ``_start_of_day`` to
    zero out the time portion.

    Args:
        dt: Any datetime within the target month.

    Returns:
        The first of the month at 00:00:00.000000, same ``tzinfo``.
    """
    return _start_of_day(dt.replace(day=1))


def _end_of_month(dt: datetime) -> datetime:
    """Return the last microsecond of the last day of the month containing *dt*.

    The algorithm avoids hard-coding month lengths or importing ``calendar``
    by advancing to the first of the *next* month and subtracting one day.
    This correctly handles February (including leap years) and 30/31-day
    months.  December is special-cased because month 13 does not exist:
    the function rolls over to January of the next year instead.

    Args:
        dt: Any datetime within the target month.

    Returns:
        The last day of the month at 23:59:59.999999, same ``tzinfo``.
    """
    if dt.month == 12:
        # Wrap around to January of the following year.
        next_month = dt.replace(year=dt.year + 1, month=1, day=1)
    else:
        next_month = dt.replace(month=dt.month + 1, day=1)
    # Subtracting one day from the 1st of the next month gives the last day
    # of the current month, then _end_of_day sets the time to 23:59:59.999999.
    return _end_of_day(next_month - timedelta(days=1))


def _start_of_quarter(dt: datetime) -> datetime:
    """Return midnight on the first day of the calendar quarter containing *dt*.

    Calendar quarters map months to start-months as follows:
        Q1 (Jan-Mar) -> 1, Q2 (Apr-Jun) -> 4, Q3 (Jul-Sep) -> 7, Q4 (Oct-Dec) -> 10.
    The formula ``((month - 1) // 3) * 3 + 1`` converts any month to the
    first month of its quarter using integer division.

    Args:
        dt: Any datetime within the target quarter.

    Returns:
        The first day of the quarter at 00:00:00.000000, same ``tzinfo``.
    """
    # Integer division maps months 1-3 -> 0, 4-6 -> 1, 7-9 -> 2, 10-12 -> 3,
    # then *3+1 converts back to the quarter's starting month (1, 4, 7, 10).
    quarter_start_month = ((dt.month - 1) // 3) * 3 + 1
    return _start_of_day(dt.replace(month=quarter_start_month, day=1))


def _end_of_quarter(dt: datetime) -> datetime:
    """Return the last microsecond of the last day of the quarter containing *dt*.

    The algorithm finds the quarter's third (final) month, advances to the
    first of that month, then uses ``_end_of_month``-style logic: subtract
    one day from the first of the *following* month to get the true last day.
    If the final month is December (month 12, meaning quarter_end_month
    would be 12 -- but the code adds 2 to get the end month), it wraps into
    the next year.

    Note: ``quarter_end_month > 12`` is currently unreachable (Q4 ends at
    month 12), but the guard is kept for defensive correctness.

    Args:
        dt: Any datetime within the target quarter.

    Returns:
        The last day of the quarter at 23:59:59.999999, same ``tzinfo``.
    """
    quarter_start_month = ((dt.month - 1) // 3) * 3 + 1
    # The last month of the quarter is always start + 2 (e.g. Q1: 1+2=3 -> March).
    quarter_end_month = quarter_start_month + 2
    if quarter_end_month > 12:
        # Defensive: wrap into next year if end month exceeds December.
        qe = dt.replace(year=dt.year + 1, month=quarter_end_month - 12, day=1)
    else:
        qe = dt.replace(month=quarter_end_month, day=1)
    # Subtract 1 day from the 1st of the end month to get the last day,
    # then ceil to 23:59:59.999999.
    return _end_of_day(qe - timedelta(days=1))


def _start_of_year(dt: datetime) -> datetime:
    """Return midnight on January 1st of the year containing *dt*.

    Args:
        dt: Any datetime within the target year.

    Returns:
        January 1 at 00:00:00.000000 of the same year, same ``tzinfo``.
    """
    return _start_of_day(dt.replace(month=1, day=1))


def _end_of_year(dt: datetime) -> datetime:
    """Return the last microsecond of December 31st of the year containing *dt*.

    Args:
        dt: Any datetime within the target year.

    Returns:
        December 31 at 23:59:59.999999 of the same year, same ``tzinfo``.
    """
    return _end_of_day(dt.replace(month=12, day=31))


class DateRange:
    """An inclusive [start, end] time interval used by every analytics query.

    ``DateRange`` is the universal currency between the date-resolution
    layer (which turns UI presets like ``"7d"`` into concrete timestamps)
    and the query engine (which passes ``start_date`` / ``end_date`` into
    SQL ``BETWEEN`` clauses).

    Both boundaries are timezone-aware UTC datetimes.  ``start_date`` is
    typically floored to midnight and ``end_date`` is either "now" (for
    open-ended presets like ``"today"``) or ceiled to 23:59:59.999999
    (for closed presets like ``"yesterday"``).

    Attributes:
        start_date: Inclusive lower bound of the range (UTC).
        end_date: Inclusive upper bound of the range (UTC).
    """

    def __init__(self, start_date: datetime, end_date: datetime):
        self.start_date = start_date
        self.end_date = end_date


def resolve_date_range(preset: DateRangePreset) -> DateRange | None:
    """Convert a human-friendly preset string into a concrete UTC date range.

    This is the primary entry-point for the date resolution engine.  The
    dashboard date-picker, CLI ``--period`` flag, and MCP tools all pass a
    preset string (e.g. ``"7d"``, ``"this_month"``, ``"last_quarter"``)
    which this function expands into a ``DateRange`` anchored to the current
    UTC time.

    Supported preset families:

    * **Sliding windows** -- ``"1h"``, ``"3h"``, ``"6h"``, ``"24h"``,
      ``"7d"``, ``"14d"``, ``"30d"``, ``"60d"``, ``"90d"``, ``"6m"``,
      ``"12m"``.  The end is "now" and the start is *N* units before now.
    * **Calendar-aligned open** -- ``"today"``, ``"this_week"``,
      ``"this_month"``, ``"this_quarter"``, ``"this_year"``.  Start is the
      beginning of the calendar period; end is "now".
    * **Calendar-aligned closed** -- ``"yesterday"``, ``"last_week"``,
      ``"last_month"``, ``"last_quarter"``, ``"last_year"``.  Both start
      and end are fully resolved (the period is complete).
    * **Unbounded / custom** -- ``"all"`` and ``"custom"`` return ``None``,
      signalling the caller to omit date filters or use explicit dates.

    Args:
        preset: One of the recognised preset strings listed above.
            Unrecognised values are treated like ``"all"`` (return ``None``).

    Returns:
        A ``DateRange`` with UTC-aware boundaries, or ``None`` when the
        preset is ``"all"``, ``"custom"``, or unknown.
    """
    now = _now()

    # Hour-based: exact sliding window (now - Nh → now)
    if preset == "1h":
        return DateRange(now - timedelta(hours=1), now)
    elif preset == "3h":
        return DateRange(now - timedelta(hours=3), now)
    elif preset == "6h":
        return DateRange(now - timedelta(hours=6), now)
    elif preset == "24h":
        return DateRange(now - timedelta(hours=24), now)
    # Calendar presets
    elif preset == "today":
        return DateRange(_start_of_day(now), now)
    elif preset == "yesterday":
        y = now - timedelta(days=1)
        return DateRange(_start_of_day(y), _end_of_day(y))
    # Day-based: startOfDay(now) - Nd → endOfDay(now)  (matches Umami)
    elif preset == "7d":
        return DateRange(_start_of_day(now) - timedelta(days=7), _end_of_day(now))
    elif preset == "14d":
        return DateRange(_start_of_day(now) - timedelta(days=14), _end_of_day(now))
    elif preset == "30d":
        return DateRange(_start_of_day(now) - timedelta(days=30), _end_of_day(now))
    elif preset == "60d":
        return DateRange(_start_of_day(now) - timedelta(days=60), _end_of_day(now))
    elif preset == "90d":
        return DateRange(_start_of_day(now) - timedelta(days=90), _end_of_day(now))
    elif preset == "6m":
        return DateRange(_start_of_day(now) - timedelta(days=180), _end_of_day(now))
    elif preset == "12m":
        return DateRange(_start_of_day(now) - timedelta(days=365), _end_of_day(now))
    elif preset == "this_week":
        return DateRange(_start_of_week(now), now)
    elif preset == "last_week":
        # Rewind to last week's Monday by subtracting 1 week from this Monday.
        lw = _start_of_week(now) - timedelta(weeks=1)
        return DateRange(lw, _end_of_week(lw))
    elif preset == "this_month":
        return DateRange(_start_of_month(now), now)
    elif preset == "last_month":
        # Jump to any day in the previous month by going 1 day before
        # this month's start, then re-derive that month's boundaries.
        lm = _start_of_month(now) - timedelta(days=1)
        lm = _start_of_month(lm)
        return DateRange(lm, _end_of_month(lm))
    elif preset == "this_quarter":
        return DateRange(_start_of_quarter(now), now)
    elif preset == "last_quarter":
        # Same trick: 1 day before this quarter's start lands in the
        # previous quarter, then derive its full boundaries.
        lq = _start_of_quarter(now) - timedelta(days=1)
        lq = _start_of_quarter(lq)
        return DateRange(lq, _end_of_quarter(lq))
    elif preset == "this_year":
        return DateRange(_start_of_year(now), now)
    elif preset == "last_year":
        ly = now.replace(year=now.year - 1)
        return DateRange(_start_of_year(ly), _end_of_year(ly))
    elif preset in ("all", "custom"):
        # "all" = no date filter; "custom" = caller provides explicit dates.
        return None
    # Unknown preset -- treat as unbounded (same as "all").
    return None


def get_comparison_range(
    range_: DateRange,
    mode: Literal["previous_period", "previous_year"],
) -> DateRange:
    """Compute a comparison date range for period-over-period analytics.

    The dashboard uses this to show percentage deltas (e.g. "+12% visitors
    vs. previous period").  Two comparison strategies are supported:

    * ``"previous_year"`` -- Shifts both boundaries back by exactly one
      calendar year.  Useful for seasonal comparisons (e.g. this December
      vs. last December).  Note: this uses ``datetime.replace(year=year-1)``
      so it will raise ``ValueError`` on Feb 29 in a non-leap year.
    * ``"previous_period"`` -- Shifts the window back by its own duration,
      producing a non-overlapping adjacent period of equal length.  The
      behaviour differs by duration:

      - **Sub-day ranges** (< 24 hours, e.g. ``"1h"``/``"3h"``/``"6h"``):
        shift both boundaries back by the exact number of hours.  This
        preserves intra-day alignment (e.g. comparing 9-12 AM today with
        9-12 AM yesterday... or the same hours earlier today).
      - **Day-or-longer ranges** (>= 24 hours): the comparison end is one
        day before the original start, and the comparison start is
        ``duration_in_days + 1`` days before the original start.  This
        guarantees no overlap and an equal number of whole days.

    Args:
        range_: The primary date range to find a comparison for.
        mode: Either ``"previous_period"`` or ``"previous_year"``.

    Returns:
        A new ``DateRange`` of the same duration, shifted into the past.
    """
    if mode == "previous_year":
        return DateRange(
            range_.start_date.replace(year=range_.start_date.year - 1),
            range_.end_date.replace(year=range_.end_date.year - 1),
        )

    diff = range_.end_date - range_.start_date
    hours = diff.total_seconds() / 3600
    days = diff.total_seconds() / 86400

    if hours < 24:
        # Sub-day range: shift both boundaries back by the exact hour count
        # so the comparison covers the same time-of-day window.
        return DateRange(
            range_.start_date - timedelta(hours=hours),
            range_.end_date - timedelta(hours=hours),
        )

    # Day-or-longer range: place the comparison window immediately before the
    # original range with no overlap.  The comparison end is 1 day before the
    # original start, and the comparison start is d+1 days before (equal width).
    d = int(days)
    return DateRange(
        range_.start_date - timedelta(days=d + 1),
        range_.start_date - timedelta(days=1),
    )


def get_auto_granularity(range_: DateRange) -> str:
    """Choose the best time-bucket granularity for a given date range.

    When the user (or the UI) requests ``granularity="auto"``, this function
    picks a bucket size that balances detail against readability, avoiding
    both "too many data points" (e.g. minute buckets over a year) and "too
    few" (e.g. monthly buckets for a 1-hour view).

    The thresholds mirror the Umami-legacy behaviour and produce roughly
    60-360 buckets for typical ranges:

    ========== ============ =======================
    Range span  Granularity  Approx. bucket count
    ========== ============ =======================
    <= 6 h      minute       up to 360
    <= 1 day    hour         up to 24
    <= 90 days  day          up to 90
    <= 365 days week         up to ~52
    > 365 days  month        varies
    ========== ============ =======================

    Args:
        range_: The date range whose span determines the granularity.

    Returns:
        One of ``"minute"``, ``"hour"``, ``"day"``, ``"week"``, or
        ``"month"``.
    """
    diff = range_.end_date - range_.start_date
    hours = diff.total_seconds() / 3600
    days = diff.total_seconds() / 86400

    if hours <= 6:
        return "minute"
    if hours <= 36:
        return "hour"
    if days <= 90:
        return "day"
    if days <= 365:
        return "week"
    return "month"


def resolve_granularity(granularity: Granularity, range_: DateRange) -> str:
    """Resolve a possibly-automatic granularity into a concrete bucket size.

    If the caller passes ``"auto"``, the function delegates to
    ``get_auto_granularity`` which inspects the date range span.
    Any other value (``"minute"``, ``"hour"``, ``"day"``, ``"week"``,
    ``"month"``) is returned as-is, trusting the caller to have validated it.

    This is the function that views and API endpoints should call -- it
    abstracts away the auto-detection so callers do not need to check the
    string themselves.

    Args:
        granularity: Either ``"auto"`` or an explicit bucket size.
        range_: The date range, needed only when *granularity* is ``"auto"``.

    Returns:
        A concrete granularity string suitable for PostgreSQL
        ``date_trunc()`` and ``generate_series()`` calls.
    """
    if granularity == "auto":
        return get_auto_granularity(range_)
    return granularity
