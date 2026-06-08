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
    - :mod:`core.mantecato_core.queries.events`
    - :mod:`core.mantecato_core.queries.stats`
"""

from __future__ import annotations

from typing import TypedDict


class WebsiteStats(TypedDict):
    """Aggregate metrics for one website over a date range.

    Returned by :func:`core.mantecato_core.queries.stats.get_website_stats`.
    """

    pageviews: int
    human_pageviews: int
    bot_pageviews: int


class PageRow(TypedDict, total=False):
    """One row in the "top pages" result set."""

    urlPath: str
    pageTitle: str | None
    views: int
    visitors: int | None


class DeviceRow(TypedDict, total=False):
    """One row in the device/browser/OS breakdown."""

    value: str
    pageviews: int
    percentage: float


class GeoRow(TypedDict, total=False):
    """One row of the geographic breakdown (country-level only)."""

    country: str
    pageviews: int


class EventRow(TypedDict, total=False):
    """One row in the custom-event analytics output."""

    eventName: str
    count: int
    visitors: int | None
    lastTriggered: str


class TimePoint(TypedDict, total=False):
    """One time-series bucket (``stats.get_pageview_time_series``)."""

    time: str
    pageviews: int
