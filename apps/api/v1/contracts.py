"""Strict request contracts and date/filter normalization for API v1."""

from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apps.api.v1.catalog import (
    COMPARE_MODES,
    DEFAULT_LIMIT,
    DIMENSIONS,
    FILTERS,
    GRANULARITIES,
    MAX_DIMENSIONS,
    MAX_LIMIT,
    METRICS,
    SCHEMA_VERSION,
)

_KNOWN_FIELDS = {
    "website_id",
    "dataset",
    "operation",
    "start",
    "end",
    "current_start",
    "current_end",
    "range",
    "timezone",
    "granularity",
    "dimensions",
    "dimension",
    "metrics",
    "metric",
    "filters",
    "filter_groups",
    "limit",
    "include_partial_bucket",
    "section_depth",
    "dimension_prefix",
    "dimension_exact",
    "previous_start",
    "previous_end",
    "compare",
    "align",
    "sort",
    "direction",
    "minimum_current",
    "minimum_previous",
    "minimum_total",
    "search",
    "thresholds",
}


class ContractError(ValueError):
    """A request cannot be normalized without changing its meaning."""

    def __init__(self, message: str, *, field: str | None = None, code: str = "INVALID_REQUEST"):
        super().__init__(message)
        self.message = message
        self.field = field
        self.code = code

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"code": self.code, "message": self.message}
        if self.field:
            result["field"] = self.field
        return result


@dataclass(frozen=True)
class ResolvedRange:
    """A half-open UTC interval with its user-facing timezone metadata."""

    start: datetime
    end: datetime
    timezone: str
    partial: bool
    preset: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "start": _iso_z(self.start),
            "end": _iso_z(self.end),
            "timezone": self.timezone,
            "partial": self.partial,
            "preset": self.preset,
        }


@dataclass(frozen=True)
class FilterSpec:
    column: str
    operator: str
    values: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        value: object = list(self.values) if self.operator in ("in", "not_in") else self.values[0]
        return {"column": self.column, "operator": self.operator, "value": value}


@dataclass(frozen=True)
class QuerySpec:
    website_id: str
    dataset: str
    operation: str
    date_range: ResolvedRange
    granularity: str | None
    dimensions: tuple[str, ...]
    metrics: tuple[str, ...]
    filter_groups: tuple[tuple[FilterSpec, ...], ...]
    limit: int
    include_partial_bucket: bool
    section_depth: int
    dimension_prefix: str | None
    dimension_exact: str | None

    @property
    def rows_are_overlapping(self) -> bool:
        return "content_group" in self.dimensions

    def query_metadata(self) -> dict[str, object]:
        return {
            "website_id": self.website_id,
            **self.date_range.as_dict(),
            "dataset": self.dataset,
            "operation": self.operation,
            "granularity": self.granularity,
            "dimensions": list(self.dimensions),
            "metrics": list(self.metrics),
            "filter_groups": [
                [filter_spec.as_dict() for filter_spec in group] for group in self.filter_groups
            ],
            "limit": self.limit,
            "partial": self.date_range.partial,
            "rows_are_overlapping": self.rows_are_overlapping,
            "dimension_prefix": self.dimension_prefix,
            "dimension_exact": self.dimension_exact,
        }


@dataclass(frozen=True)
class CompareSpec:
    query: QuerySpec
    previous: ResolvedRange
    metric: str
    sort: str
    direction: str
    minimum_current: float
    minimum_previous: float
    minimum_total: float


@dataclass(frozen=True)
class TrafficQualitySpec:
    query: QuerySpec
    previous: ResolvedRange | None
    thresholds: dict[str, float]


def parse_query(data: object, *, now: datetime | None = None) -> QuerySpec:
    """Parse a query request without permissive fallback behavior."""
    body = _body_dict(data)
    unknown_fields = sorted(set(body) - _KNOWN_FIELDS)
    if unknown_fields:
        raise ContractError(
            f"unknown request field(s): {', '.join(unknown_fields)}",
            field=unknown_fields[0],
        )
    website_id = _required_uuid(body, "website_id")
    operation = str(body.get("operation") or "totals")
    if operation not in ("totals", "timeseries", "breakdown"):
        raise ContractError("operation must be totals, timeseries, or breakdown", field="operation")

    raw_dimensions = body.get("dimensions")
    if raw_dimensions is None and body.get("dimension") is not None:
        raw_dimensions = [body["dimension"]]
    dimensions = _string_tuple(raw_dimensions or [], field="dimensions")
    if len(dimensions) > MAX_DIMENSIONS:
        raise ContractError(
            f"at most {MAX_DIMENSIONS} dimensions are supported", field="dimensions"
        )
    unknown_dimensions = sorted(set(dimensions) - set(DIMENSIONS))
    if unknown_dimensions:
        raise ContractError(
            f"unknown dimension(s): {', '.join(unknown_dimensions)}",
            field="dimensions",
        )

    metrics = _string_tuple(body.get("metrics") or ["pageviews"], field="metrics")
    unknown_metrics = sorted(set(metrics) - set(METRICS))
    if unknown_metrics:
        raise ContractError(f"unknown metric(s): {', '.join(unknown_metrics)}", field="metrics")

    dataset = str(body.get("dataset") or _infer_dataset(dimensions, metrics))
    if dataset not in ("pageviews", "events"):
        raise ContractError("dataset must be pageviews or events", field="dataset")
    _validate_dataset(dataset, dimensions, metrics)

    granularity = body.get("granularity")
    if granularity is not None:
        granularity = str(granularity)
        if granularity not in GRANULARITIES:
            raise ContractError(
                f"granularity must be one of: {', '.join(GRANULARITIES)}",
                field="granularity",
            )
    if operation == "timeseries" and granularity is None:
        granularity = "day"
    if operation != "timeseries" and granularity is not None:
        raise ContractError("granularity is only valid for timeseries", field="granularity")
    if operation == "totals" and dimensions:
        raise ContractError("totals does not accept dimensions", field="dimensions")
    if operation == "breakdown" and not dimensions:
        raise ContractError("breakdown requires at least one dimension", field="dimensions")

    include_partial = bool(body.get("include_partial_bucket", True))
    date_range = resolve_range(
        body, now=now, granularity=granularity, include_partial=include_partial
    )
    limit = _bounded_int(body.get("limit", DEFAULT_LIMIT), "limit", 1, MAX_LIMIT)
    section_depth = _bounded_int(body.get("section_depth", 2), "section_depth", 1, 6)
    dimension_prefix = _optional_string(body.get("dimension_prefix"), "dimension_prefix")
    dimension_exact = _optional_string(body.get("dimension_exact"), "dimension_exact")
    if dimension_prefix and dimension_exact:
        raise ContractError(
            "dimension_prefix and dimension_exact are mutually exclusive",
            field="dimension_prefix",
        )
    if (dimension_prefix or dimension_exact) and "content_group" not in dimensions:
        raise ContractError(
            "dimension selectors currently require the content_group dimension",
            field="dimension_prefix",
        )
    filter_groups = parse_filter_groups(body)

    return QuerySpec(
        website_id=website_id,
        dataset=dataset,
        operation=operation,
        date_range=date_range,
        granularity=granularity,
        dimensions=dimensions,
        metrics=metrics,
        filter_groups=filter_groups,
        limit=limit,
        include_partial_bucket=include_partial,
        section_depth=section_depth,
        dimension_prefix=dimension_prefix,
        dimension_exact=dimension_exact,
    )


def parse_compare(data: object, *, now: datetime | None = None) -> CompareSpec:
    """Parse a comparison request with explicit or derived previous range."""
    body = _body_dict(data)
    query_body = dict(body)
    if query_body.get("start") is None and query_body.get("current_start") is not None:
        query_body["start"] = query_body["current_start"]
    if query_body.get("end") is None and query_body.get("current_end") is not None:
        query_body["end"] = query_body["current_end"]
    query_body["operation"] = "breakdown"
    metric = str(body.get("metric") or "pageviews")
    query_body["metrics"] = [metric]
    query = parse_query(query_body, now=now)

    previous_body: dict[str, Any]
    if body.get("previous_start") is not None or body.get("previous_end") is not None:
        if body.get("previous_start") is None or body.get("previous_end") is None:
            raise ContractError(
                "previous_start and previous_end must be supplied together",
                field="previous_start",
            )
        previous_body = {
            "start": body["previous_start"],
            "end": body["previous_end"],
            "timezone": body.get("timezone", "UTC"),
        }
        previous = resolve_range(previous_body, now=now)
    else:
        mode = str(body.get("compare") or "previous_period")
        if mode not in COMPARE_MODES:
            raise ContractError(
                f"compare must be one of: {', '.join(COMPARE_MODES)}",
                field="compare",
            )
        previous = comparison_range(query.date_range, mode)

    align = str(body.get("align") or "full")
    if align not in ("full", "elapsed"):
        raise ContractError("align must be full or elapsed", field="align")
    if align == "elapsed":
        elapsed = query.date_range.end - query.date_range.start
        available = previous.end - previous.start
        if elapsed <= timedelta(0) or elapsed > available:
            raise ContractError(
                "comparison period cannot be aligned to the current elapsed duration",
                field="align",
                code="UNALIGNABLE_PERIODS",
            )
        previous = ResolvedRange(
            start=previous.start,
            end=previous.start + elapsed,
            timezone=previous.timezone,
            partial=previous.partial,
            preset=previous.preset,
        )

    sort = str(body.get("sort") or "absolute_change")
    valid_sorts = {
        "current",
        "previous",
        "absolute_change",
        "percentage_change",
        "contribution",
    }
    if sort not in valid_sorts:
        raise ContractError(f"sort must be one of: {', '.join(sorted(valid_sorts))}", field="sort")
    direction = str(body.get("direction") or "both")
    if direction not in ("gains", "losses", "both"):
        raise ContractError("direction must be gains, losses, or both", field="direction")

    return CompareSpec(
        query=query,
        previous=previous,
        metric=metric,
        sort=sort,
        direction=direction,
        minimum_current=_nonnegative_float(body.get("minimum_current", 0), "minimum_current"),
        minimum_previous=_nonnegative_float(body.get("minimum_previous", 0), "minimum_previous"),
        minimum_total=_nonnegative_float(body.get("minimum_total", 0), "minimum_total"),
    )


def parse_traffic_quality(data: object, *, now: datetime | None = None) -> TrafficQualitySpec:
    """Parse a traffic-quality request."""
    body = _body_dict(data)
    query_body = dict(body)
    query_body["operation"] = "breakdown"
    query_body["metrics"] = [
        "pageviews",
        "daily_unique_visitors",
        "visits",
        "bounces",
        "human_pageviews",
        "bot_pageviews",
    ]
    query = parse_query(query_body, now=now)
    previous = None
    if body.get("compare") or body.get("previous_start") or body.get("previous_end"):
        compare_body = dict(body)
        compare_body["metric"] = "pageviews"
        previous = parse_compare(compare_body, now=now).previous

    defaults = {
        "high_pages_per_visitor": 10.0,
        "high_one_page_share": 90.0,
        "single_browser_concentration": 90.0,
        "single_device_concentration": 90.0,
        "sudden_volume_change": 100.0,
        "minimum_pageviews": 20.0,
    }
    supplied = body.get("thresholds") or {}
    if not isinstance(supplied, dict):
        raise ContractError("thresholds must be an object", field="thresholds")
    for key, value in supplied.items():
        if key not in defaults:
            raise ContractError(f"unknown threshold: {key}", field="thresholds")
        defaults[key] = _nonnegative_float(value, f"thresholds.{key}")
    return TrafficQualitySpec(query=query, previous=previous, thresholds=defaults)


def resolve_range(
    body: dict[str, Any],
    *,
    now: datetime | None = None,
    granularity: str | None = None,
    include_partial: bool = True,
) -> ResolvedRange:
    """Resolve explicit or preset boundaries into a half-open UTC interval."""
    current = (now or datetime.now(UTC)).astimezone(UTC)
    timezone_name = str(body.get("timezone") or "UTC")
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ContractError("unknown IANA timezone", field="timezone") from exc

    start_raw, end_raw = body.get("start"), body.get("end")
    if (start_raw is None) != (end_raw is None):
        raise ContractError("start and end must be supplied together", field="start")

    preset: str | None = None
    if start_raw is not None:
        start = _parse_boundary(start_raw, zone, field="start")
        end = _parse_boundary(end_raw, zone, field="end")
    else:
        preset = str(body.get("range") or "30d")
        start, end = _preset_range(preset, current, zone)

    if end <= start:
        raise ContractError("end must be after start", field="end", code="REVERSED_RANGE")

    bucket_granularity = granularity or "day"
    end_local = min(end, current).astimezone(zone)
    partial = end > current or end_local != _floor(end_local, bucket_granularity)
    effective_end = min(end, current) if end > current else end
    if not include_partial and granularity and partial and effective_end > start:
        local_end = effective_end.astimezone(zone)
        complete_local = _floor(local_end, granularity)
        complete_end = complete_local.astimezone(UTC)
        if complete_end > start:
            effective_end = complete_end
        else:
            raise ContractError(
                "excluding the partial bucket leaves an empty range",
                field="include_partial_bucket",
            )
    return ResolvedRange(
        start=start, end=effective_end, timezone=timezone_name, partial=partial, preset=preset
    )


def comparison_range(current: ResolvedRange, mode: str) -> ResolvedRange:
    """Derive a half-open comparison interval from a resolved current range."""
    zone = ZoneInfo(current.timezone)
    if mode == "previous_period":
        duration = current.end - current.start
        start, end = current.start - duration, current.start
    elif mode == "previous_week":
        start = _shift_local_days(current.start, zone, -7)
        end = _shift_local_days(current.end, zone, -7)
    elif mode == "previous_year":
        start = _shift_local_year(current.start, zone, -1)
        end = _shift_local_year(current.end, zone, -1)
    else:  # pragma: no cover - callers validate
        raise ContractError("invalid comparison mode", field="compare")
    return ResolvedRange(
        start=start, end=end, timezone=current.timezone, partial=False, preset=mode
    )


def parse_filter_groups(body: dict[str, Any]) -> tuple[tuple[FilterSpec, ...], ...]:
    """Parse independent filter groups; groups are ANDed by the SQL builder."""
    raw_groups: list[object] = []
    if body.get("filters"):
        raw_groups.append(body["filters"])
    supplied_groups = body.get("filter_groups") or []
    if not isinstance(supplied_groups, list):
        raise ContractError("filter_groups must be an array", field="filter_groups")
    raw_groups.extend(supplied_groups)

    groups: list[tuple[FilterSpec, ...]] = []
    for raw_group in raw_groups:
        if not isinstance(raw_group, list):
            raise ContractError("each filter group must be an array", field="filter_groups")
        group = tuple(_parse_filter(item) for item in raw_group)
        if group:
            groups.append(group)
    return tuple(groups)


def schema_document() -> dict[str, object]:
    """Return a bounded JSON-schema-like document without an extra dependency."""
    return {
        "schema_version": SCHEMA_VERSION,
        "query": {
            "required": ["website_id"],
            "properties": {
                "website_id": {"type": "string", "format": "uuid"},
                "operation": {"enum": ["totals", "timeseries", "breakdown"]},
                "start": {"type": "string", "format": "date-time-or-date"},
                "end": {"type": "string", "format": "date-time-or-date", "exclusive": True},
                "range": {"type": "string"},
                "timezone": {"type": "string", "default": "UTC"},
                "granularity": {"enum": list(GRANULARITIES)},
                "dimensions": {"type": "array", "items": {"enum": sorted(DIMENSIONS)}},
                "metrics": {"type": "array", "items": {"enum": sorted(METRICS)}},
                "filters": {"type": "array"},
                "filter_groups": {"type": "array"},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
                "dimension_prefix": {"type": "string"},
                "dimension_exact": {"type": "string"},
            },
        },
    }


def _body_dict(data: object) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ContractError("request body must be a JSON object")
    return dict(data)


def _required_uuid(body: dict[str, Any], key: str) -> str:
    value = _required_string(body, key)
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise ContractError(f"{key} must be a UUID", field=key) from exc


def _optional_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string", field=field)
    return value.strip()


def _required_string(body: dict[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{key} is required", field=key)
    return value.strip()


def _string_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if isinstance(value, str):
        values = [part.strip() for part in value.split(",") if part.strip()]
    elif isinstance(value, list):
        values = value
    else:
        raise ContractError(f"{field} must be an array or comma-separated string", field=field)
    if not all(isinstance(item, str) and item.strip() for item in values):
        raise ContractError(f"{field} contains an invalid value", field=field)
    normalized = tuple(item.strip() for item in values)
    if len(set(normalized)) != len(normalized):
        raise ContractError(f"{field} contains duplicates", field=field)
    return normalized


def _infer_dataset(dimensions: tuple[str, ...], metrics: tuple[str, ...]) -> str:
    if "event_name" in dimensions or "events" in metrics:
        return "events"
    return "pageviews"


def _validate_dataset(dataset: str, dimensions: tuple[str, ...], metrics: tuple[str, ...]) -> None:
    for dimension in dimensions:
        required = DIMENSIONS[dimension]["dataset"]
        if required != dataset:
            raise ContractError(
                f"dimension {dimension} requires dataset {required}",
                field="dimensions",
            )
    for metric in metrics:
        required = METRICS[metric]["dataset"]
        if required not in ("both", dataset):
            raise ContractError(f"metric {metric} requires dataset {required}", field="metrics")


def _parse_filter(item: object) -> FilterSpec:
    if isinstance(item, str):
        parts = item.split(":", 2)
        if len(parts) != 3:
            raise ContractError(
                "filters must use column:operator:value",
                field="filters",
                code="INVALID_FILTER",
            )
        column, operator, raw_value = parts
        if operator in ("in", "not_in"):
            try:
                values = tuple(
                    value.strip()
                    for value in next(csv.reader(io.StringIO(raw_value), skipinitialspace=True))
                    if value.strip()
                )
            except (csv.Error, StopIteration) as exc:
                raise ContractError("invalid CSV membership value", field="filters") from exc
        else:
            values = (raw_value,)
    elif isinstance(item, dict):
        column = str(item.get("column") or "")
        operator = str(item.get("operator") or "")
        raw_value = item.get("value")
        if operator in ("in", "not_in"):
            if isinstance(raw_value, list):
                values = tuple(str(value) for value in raw_value if str(value))
            elif isinstance(raw_value, str):
                values = tuple(part.strip() for part in raw_value.split(",") if part.strip())
            else:
                values = ()
        else:
            values = (str(raw_value),) if raw_value is not None else ()
    else:
        raise ContractError("filter must be a string or object", field="filters")

    if column not in FILTERS:
        raise ContractError(
            f"unknown filter column {column}; valid columns: {', '.join(sorted(FILTERS))}",
            field="filters",
            code="INVALID_FILTER",
        )
    if operator not in FILTERS[column]:
        raise ContractError(
            f"operator {operator} is not valid for {column}; valid operators: "
            f"{', '.join(FILTERS[column])}",
            field="filters",
            code="INVALID_FILTER",
        )
    if not values:
        raise ContractError("filter value cannot be empty", field="filters", code="INVALID_FILTER")
    if column == "is_bot":
        lowered = values[0].lower()
        if lowered not in ("true", "false", "1", "0"):
            raise ContractError("is_bot accepts true or false", field="filters")
        values = ("true" if lowered in ("true", "1") else "false",)
    return FilterSpec(column=column, operator=operator, values=values)


def _parse_boundary(value: object, zone: ZoneInfo, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be an ISO-8601 date or timestamp", field=field)
    raw = value.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            parsed = datetime.combine(date.fromisoformat(raw), time.min, tzinfo=zone)
        else:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = _localize_strict(parsed, zone, field)
    except ValueError as exc:
        raise ContractError(f"{field} is not a valid ISO-8601 value", field=field) from exc
    return parsed.astimezone(UTC)


def _localize_strict(value: datetime, zone: ZoneInfo, field: str) -> datetime:
    first = value.replace(tzinfo=zone, fold=0)
    second = value.replace(tzinfo=zone, fold=1)
    first_roundtrip = first.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
    second_roundtrip = second.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
    valid_first = first_roundtrip == value
    valid_second = second_roundtrip == value
    if not valid_first and not valid_second:
        raise ContractError("local timestamp does not exist because of DST", field=field)
    if valid_first and valid_second and first.utcoffset() != second.utcoffset():
        raise ContractError("local timestamp is ambiguous; include an explicit offset", field=field)
    return first if valid_first else second


def _preset_range(preset: str, now: datetime, zone: ZoneInfo) -> tuple[datetime, datetime]:
    local_now = now.astimezone(zone)
    if preset in ("1h", "3h", "6h", "24h"):
        return now - timedelta(hours=int(preset[:-1])), now
    if preset in ("7d", "14d", "30d", "60d", "90d"):
        start_local = datetime.combine(
            local_now.date() - timedelta(days=int(preset[:-1])),
            time.min,
            tzinfo=zone,
        )
        return start_local.astimezone(UTC), now
    if preset == "today":
        return datetime.combine(local_now.date(), time.min, tzinfo=zone).astimezone(UTC), now
    if preset == "yesterday":
        day = local_now.date() - timedelta(days=1)
        return (
            datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC),
            datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC),
        )
    if preset in ("6m", "12m"):
        days = 180 if preset == "6m" else 365
        start_day = local_now.date() - timedelta(days=days)
        return datetime.combine(start_day, time.min, tzinfo=zone).astimezone(UTC), now
    this_week = local_now.date() - timedelta(days=local_now.weekday())
    if preset == "this_week":
        return datetime.combine(this_week, time.min, tzinfo=zone).astimezone(UTC), now
    if preset == "last_week":
        start_day = this_week - timedelta(days=7)
        return _local_day_range(start_day, start_day + timedelta(days=7), zone)
    this_month = local_now.date().replace(day=1)
    if preset == "this_month":
        return datetime.combine(this_month, time.min, tzinfo=zone).astimezone(UTC), now
    if preset == "last_month":
        previous_end = this_month
        previous_start = (this_month - timedelta(days=1)).replace(day=1)
        return _local_day_range(previous_start, previous_end, zone)
    quarter_month = ((local_now.month - 1) // 3) * 3 + 1
    this_quarter = local_now.date().replace(month=quarter_month, day=1)
    if preset == "this_quarter":
        return datetime.combine(this_quarter, time.min, tzinfo=zone).astimezone(UTC), now
    if preset == "last_quarter":
        previous_end = this_quarter
        previous_month = quarter_month - 3
        year = local_now.year
        if previous_month <= 0:
            previous_month += 12
            year -= 1
        previous_start = date(year, previous_month, 1)
        return _local_day_range(previous_start, previous_end, zone)
    this_year = local_now.date().replace(month=1, day=1)
    if preset == "this_year":
        return datetime.combine(this_year, time.min, tzinfo=zone).astimezone(UTC), now
    if preset == "last_year":
        return _local_day_range(
            date(local_now.year - 1, 1, 1),
            date(local_now.year, 1, 1),
            zone,
        )
    raise ContractError("unknown date range preset", field="range", code="INVALID_RANGE")


def _local_day_range(start: date, end: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    return (
        datetime.combine(start, time.min, tzinfo=zone).astimezone(UTC),
        datetime.combine(end, time.min, tzinfo=zone).astimezone(UTC),
    )


def _floor(value: datetime, granularity: str) -> datetime:
    if granularity == "minute":
        return value.replace(second=0, microsecond=0)
    if granularity == "hour":
        return value.replace(minute=0, second=0, microsecond=0)
    if granularity == "day":
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    if granularity == "week":
        day = value - timedelta(days=value.weekday())
        return day.replace(hour=0, minute=0, second=0, microsecond=0)
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _shift_local_days(value: datetime, zone: ZoneInfo, days: int) -> datetime:
    local = value.astimezone(zone)
    shifted = local.replace(tzinfo=None) + timedelta(days=days)
    return shifted.replace(tzinfo=zone).astimezone(UTC)


def _shift_local_year(value: datetime, zone: ZoneInfo, years: int) -> datetime:
    local = value.astimezone(zone)
    try:
        shifted = local.replace(year=local.year + years)
    except ValueError:
        shifted = local.replace(year=local.year + years, day=28)
    return shifted.astimezone(UTC)


def _bounded_int(value: object, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ContractError(f"{field} must be an integer", field=field)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{field} must be an integer", field=field) from exc
    if not minimum <= parsed <= maximum:
        raise ContractError(f"{field} must be between {minimum} and {maximum}", field=field)
    return parsed


def _nonnegative_float(value: object, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{field} must be numeric", field=field) from exc
    if parsed < 0:
        raise ContractError(f"{field} cannot be negative", field=field)
    return parsed


def _iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
