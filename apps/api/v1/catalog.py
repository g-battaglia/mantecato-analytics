"""Machine-readable analytics capabilities for API v1."""

from __future__ import annotations

SCHEMA_VERSION = "1"

DIMENSIONS: dict[str, dict[str, object]] = {
    "country": {"dataset": "pageviews", "overlapping": False},
    "referrer_domain": {"dataset": "pageviews", "overlapping": False},
    "browser": {"dataset": "pageviews", "overlapping": False},
    "os": {"dataset": "pageviews", "overlapping": False},
    "device": {"dataset": "pageviews", "overlapping": False},
    "hostname": {"dataset": "pageviews", "overlapping": False},
    "url_path": {"dataset": "pageviews", "overlapping": False},
    "page_title": {"dataset": "pageviews", "overlapping": False},
    "content_group": {"dataset": "pageviews", "overlapping": True},
    "section": {"dataset": "pageviews", "overlapping": False},
    "event_name": {"dataset": "events", "overlapping": False},
}

METRICS: dict[str, dict[str, object]] = {
    "pageviews": {"dataset": "pageviews", "unit": "count", "additive": True},
    "daily_unique_visitors": {
        "dataset": "both",
        "unit": "count",
        "additive": False,
        "method": "sum_of_utc_day_distinct_ephemeral_digests",
    },
    "visits": {"dataset": "pageviews", "unit": "count", "additive": False},
    "bounces": {"dataset": "pageviews", "unit": "count", "additive": False},
    "bounce_rate": {"dataset": "pageviews", "unit": "percent", "additive": False},
    "total_duration": {"dataset": "pageviews", "unit": "seconds", "additive": False},
    "average_visit_duration": {
        "dataset": "pageviews",
        "unit": "seconds",
        "additive": False,
    },
    "pages_per_visit": {"dataset": "pageviews", "unit": "ratio", "additive": False},
    "human_pageviews": {"dataset": "pageviews", "unit": "count", "additive": True},
    "bot_pageviews": {"dataset": "pageviews", "unit": "count", "additive": True},
    "events": {"dataset": "events", "unit": "count", "additive": True},
}

FILTERS: dict[str, tuple[str, ...]] = {
    "url_path": (
        "eq",
        "neq",
        "contains",
        "not_contains",
        "starts_with",
        "not_starts_with",
        "in",
        "not_in",
    ),
    "page_title": (
        "eq",
        "neq",
        "contains",
        "not_contains",
        "starts_with",
        "not_starts_with",
        "in",
        "not_in",
    ),
    "hostname": (
        "eq",
        "neq",
        "contains",
        "not_contains",
        "starts_with",
        "not_starts_with",
        "in",
        "not_in",
    ),
    "browser": (
        "eq",
        "neq",
        "contains",
        "not_contains",
        "starts_with",
        "not_starts_with",
        "in",
        "not_in",
    ),
    "os": (
        "eq",
        "neq",
        "contains",
        "not_contains",
        "starts_with",
        "not_starts_with",
        "in",
        "not_in",
    ),
    "device": (
        "eq",
        "neq",
        "contains",
        "not_contains",
        "starts_with",
        "not_starts_with",
        "in",
        "not_in",
    ),
    "country": ("eq", "neq", "in", "not_in"),
    "event_name": (
        "eq",
        "neq",
        "contains",
        "not_contains",
        "starts_with",
        "not_starts_with",
        "in",
        "not_in",
    ),
    "referrer_domain": (
        "eq",
        "neq",
        "contains",
        "not_contains",
        "starts_with",
        "not_starts_with",
        "in",
        "not_in",
    ),
    "content_group": ("eq", "neq", "starts_with", "not_starts_with", "in", "not_in"),
    "is_bot": ("eq", "neq"),
}

GRANULARITIES = ("minute", "hour", "day", "week", "month")
COMPARE_MODES = ("previous_period", "previous_week", "previous_year")
MAX_DIMENSIONS = 2
DEFAULT_LIMIT = 50
MAX_LIMIT = 500
MAX_CARDINALITY = 5_000
MAX_BUCKETS = 2_000
STATEMENT_TIMEOUT_MS = 20_000


def capabilities() -> dict[str, object]:
    """Return the public API v1 capability document."""
    return {
        "schema_version": SCHEMA_VERSION,
        "api_version": "v1",
        "operations": [
            "query",
            "compare",
            "traffic_quality",
            "dimension_values",
        ],
        "dimensions": DIMENSIONS,
        "metrics": METRICS,
        "filters": {name: list(operators) for name, operators in FILTERS.items()},
        "granularities": list(GRANULARITIES),
        "compare_modes": list(COMPARE_MODES),
        "limits": {
            "max_dimensions": MAX_DIMENSIONS,
            "max_rows": MAX_LIMIT,
            "max_cardinality": MAX_CARDINALITY,
            "max_buckets": MAX_BUCKETS,
            "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
        },
    }
