"""mantecato-core: sync query engine for Django + psycopg3.

SQL execution goes through ``django.db.connections['default'].cursor()``.
Parameter placeholders use ``{{name}}`` / ``{{name::type}}`` syntax.
"""

from .database import paged_raw_query, raw_query, raw_query_one
from .date_utils import (
    DateRange,
    get_auto_granularity,
    get_comparison_range,
    resolve_date_range,
    resolve_granularity,
)
from .filters import Filter, apply_filters, build_filter_sql, parse_filters_from_params
from .helpers import (
    compute_derived_stats,
    format_duration,
    format_percent,
    list_sites,
    num,
    parse_date_args,
    parse_filter_args,
    pct_change,
    resolve_granularity_arg,
    resolve_site_id,
)

__all__ = [
    "raw_query",
    "raw_query_one",
    "paged_raw_query",
    "Filter",
    "build_filter_sql",
    "parse_filters_from_params",
    "apply_filters",
    "DateRange",
    "resolve_date_range",
    "resolve_granularity",
    "get_comparison_range",
    "get_auto_granularity",
    "list_sites",
    "resolve_site_id",
    "parse_date_args",
    "parse_filter_args",
    "resolve_granularity_arg",
    "compute_derived_stats",
    "num",
    "pct_change",
    "format_duration",
    "format_percent",
]
