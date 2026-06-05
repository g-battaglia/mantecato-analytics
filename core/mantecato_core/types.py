"""TypedDict shapes for the raw-SQL query engine.

These declarations document the row shapes returned by the query functions
in :mod:`core.mantecato_core.queries`. They are pure type hints — runtime
behaviour is unchanged — so they cost nothing at import time but give
editors (Pyright, PyCharm, mypy) full auto-completion when consuming
results from the service layer.

Naming convention:
    ``*Row``: a single row of a result set returned by a query function.
    ``*Stats``: aggregate dicts (single-row summaries).

Cross-refs:
    - :mod:`core.mantecato_core.queries.pageviews`
    - :mod:`core.mantecato_core.queries.sources`
    - :mod:`core.mantecato_core.queries.engagement`
    - :mod:`core.mantecato_core.queries.stats`
"""

from __future__ import annotations

from typing import TypedDict


class WebsiteStats(TypedDict):
    """Aggregate metrics for one website over a date range.

    Returned by :func:`core.mantecato_core.queries.stats.get_website_stats`.
    """

    pageviews: int
    visitors: int
    visits: int
    bounces: int
    totaltime: int


class PageRow(TypedDict, total=False):
    """One row in the "top pages" result set."""

    url: str
    pageviews: int
    visitors: int
    bounce_rate: float


class SourceRow(TypedDict, total=False):
    """One row in the referrer/channel/UTM result sets."""

    value: str
    visitors: int
    visits: int
    pageviews: int


class DeviceRow(TypedDict, total=False):
    """One row in the device/browser/OS breakdown."""

    value: str
    visitors: int


class GeoRow(TypedDict, total=False):
    """One row of the geographic breakdown (country/region/city)."""

    country: str
    region: str
    city: str
    visitors: int


class EventRow(TypedDict, total=False):
    """One row in the custom-event analytics output."""

    event_name: str
    count: int
    visitors: int


class SessionRow(TypedDict, total=False):
    """One row in the session-list response."""

    session_id: str
    visitors: int
    pageviews: int
    duration_seconds: int
    started_at: str


class FunnelStepRow(TypedDict, total=False):
    """One step in a funnel analysis result."""

    label: str
    visitors: int
    dropoff: int
    conversion_rate: float


class JourneyRow(TypedDict, total=False):
    """One ordered path in the user-journey result set."""

    path: list[str]
    count: int


class RetentionCohort(TypedDict, total=False):
    """One cohort row in the retention matrix.

    ``values`` is the per-period retention ratio (0..1), ordered from week 0
    onwards.
    """

    cohort_date: str
    cohort_size: int
    values: list[float]


class RevenueRow(TypedDict, total=False):
    """One row in the revenue summary / by-country / by-event tables."""

    value: str
    revenue: float
    currency: str
    count: int


class TimePoint(TypedDict, total=False):
    """One time-series bucket (``stats.get_pageview_time_series``)."""

    time: str
    pageviews: int
    visitors: int
