"""Service layer for API v1 analytics responses."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from apps.api.v1.catalog import METRICS, SCHEMA_VERSION
from apps.api.v1.queries import aggregate

if TYPE_CHECKING:
    from apps.api.v1.contracts import CompareSpec, QuerySpec, ResolvedRange, TrafficQualitySpec


def run_query(spec: QuerySpec) -> dict[str, Any]:
    """Execute one normalized analytics query and return the v1 envelope."""
    rows, cardinality_overflow = aggregate(spec)
    if cardinality_overflow:
        raise QueryLimitError("dimension cardinality exceeds the server limit")
    selected, truncated = _limit_rows(spec, rows)
    totals = _independent_totals(spec)
    return {
        "schema_version": SCHEMA_VERSION,
        "query": {**spec.query_metadata(), "truncated": truncated},
        "comparison": None,
        "totals": totals,
        "rows": [_public_row(row) for row in selected],
        "metric_metadata": _metric_metadata(spec.metrics),
    }


def run_compare(spec: CompareSpec) -> dict[str, Any]:
    """Compare complete dimension sets before sorting and limiting."""
    current_rows, current_overflow = aggregate(spec.query)
    previous_rows, previous_overflow = aggregate(spec.query, date_range=spec.previous)
    if current_overflow or previous_overflow:
        raise QueryLimitError("comparison cardinality exceeds the server limit")

    current_total = _metric_total(spec.query, spec.query.date_range, spec.metric)
    previous_total = _metric_total(spec.query, spec.previous, spec.metric)
    total_change = _subtract(current_total, previous_total)
    dimensions = spec.query.dimensions

    current = {_dimension_key(row, dimensions): row for row in current_rows}
    previous = {_dimension_key(row, dimensions): row for row in previous_rows}
    combined: list[dict[str, Any]] = []
    for key in current.keys() | previous.keys():
        current_row = current.get(key, {})
        previous_row = previous.get(key, {})
        current_value = current_row.get(spec.metric)
        previous_value = previous_row.get(spec.metric)
        cur = 0 if current_value is None and not current_row else current_value
        prev = 0 if previous_value is None and not previous_row else previous_value
        absolute = _subtract(cur, prev)
        percentage = None
        if prev not in (None, 0) and cur is not None:
            percentage = (cur - prev) / prev * 100
        share = None
        additive = bool(METRICS[spec.metric]["additive"])
        overlapping = spec.query.rows_are_overlapping
        if additive and not overlapping and current_total not in (None, 0) and cur is not None:
            share = cur / current_total * 100
        contribution = None
        if additive and not overlapping and total_change not in (None, 0) and absolute is not None:
            contribution = absolute / total_change * 100

        row: dict[str, Any] = {}
        for index, dimension in enumerate(dimensions):
            row[dimension] = key[index]
            row[f"{dimension}_label"] = current_row.get(f"{dimension}_label") or previous_row.get(
                f"{dimension}_label"
            )
        row.update(
            {
                "current": cur,
                "previous": prev,
                "absolute_change": absolute,
                "percentage_change": percentage,
                "share_of_current": share,
                "contribution_to_total_change": contribution,
            }
        )
        unavailable: dict[str, str] = {}
        if current_value is None and current_row:
            unavailable["current"] = _reason(current_row, spec.metric)
        if previous_value is None and previous_row:
            unavailable["previous"] = _reason(previous_row, spec.metric)
        if not additive or overlapping:
            unavailable["share_of_current"] = "metric_or_dimension_is_not_additive"
            unavailable["contribution_to_total_change"] = "metric_or_dimension_is_not_additive"
        if unavailable:
            row["unavailable_reasons"] = unavailable
        if _keep_comparison_row(row, spec):
            combined.append(row)

    sort_key = "contribution_to_total_change" if spec.sort == "contribution" else spec.sort
    combined.sort(
        key=lambda row: (
            row.get(sort_key) is None,
            -abs(row.get(sort_key) or 0)
            if sort_key in ("absolute_change", "percentage_change", "contribution_to_total_change")
            else -(row.get(sort_key) or 0),
            tuple(str(value or "") for value in _dimension_key(row, dimensions)),
        )
    )
    truncated = len(combined) > spec.query.limit
    return {
        "schema_version": SCHEMA_VERSION,
        "query": {**spec.query.query_metadata(), "truncated": truncated},
        "comparison": spec.previous.as_dict(),
        "totals": {
            "current": current_total,
            "previous": previous_total,
            "absolute_change": total_change,
            "percentage_change": (
                (current_total - previous_total) / previous_total * 100
                if current_total is not None and previous_total not in (None, 0)
                else None
            ),
        },
        "rows": combined[: spec.query.limit],
        "metric_metadata": _metric_metadata((spec.metric,)),
    }


def run_traffic_quality(spec: TrafficQualitySpec) -> dict[str, Any]:
    """Return transparent heuristics without changing stored bot classification."""
    rows, overflow = aggregate(spec.query)
    if overflow:
        raise QueryLimitError("traffic-quality cardinality exceeds the server limit")
    previous_by_key: dict[tuple[object, ...], dict[str, Any]] = {}
    if spec.previous:
        previous_rows, previous_overflow = aggregate(spec.query, date_range=spec.previous)
        if previous_overflow:
            raise QueryLimitError("comparison cardinality exceeds the server limit")
        previous_by_key = {_dimension_key(row, spec.query.dimensions): row for row in previous_rows}

    browser_dominance = _dominance(spec.query, "browser")
    device_dominance = _dominance(spec.query, "device")
    output: list[dict[str, Any]] = []
    for row in rows[: spec.query.limit]:
        key = _dimension_key(row, spec.query.dimensions)
        pageviews = row.get("pageviews")
        visitors = row.get("daily_unique_visitors")
        visits = row.get("visits")
        bounces = row.get("bounces")
        bot_pageviews = row.get("bot_pageviews")
        previous_pageviews = previous_by_key.get(key, {}).get("pageviews")
        browser = browser_dominance.get(key)
        device = device_dominance.get(key)
        result = {dimension: row.get(dimension) for dimension in spec.query.dimensions}
        result.update(
            {
                "pageviews": pageviews,
                "daily_unique_visitors": visitors,
                "visits": visits,
                "pages_per_visit": _ratio(pageviews, visits),
                "pages_per_daily_unique_visitor": _ratio(pageviews, visitors),
                "bounce_rate": _percent(bounces, visits),
                "one_page_visit_share": _percent(bounces, visits),
                "direct_traffic_share": _percent(row.get("_direct_count"), pageviews),
                "bot_pageviews": bot_pageviews,
                "stored_bot_share": _percent(bot_pageviews, pageviews),
                "dominant_browser": browser[0] if browser else None,
                "dominant_browser_share": browser[1] if browser else None,
                "dominant_device": device[0] if device else None,
                "dominant_device_share": device[1] if device else None,
                "previous_pageviews": previous_pageviews,
                "pageview_change_percent": (
                    (pageviews - previous_pageviews) / previous_pageviews * 100
                    if pageviews is not None and previous_pageviews not in (None, 0)
                    else None
                ),
            }
        )
        result["indicators"] = _indicators(result, spec.thresholds)
        if row.get("unavailable_reasons"):
            result["unavailable_reasons"] = row["unavailable_reasons"]
        output.append(result)

    return {
        "schema_version": SCHEMA_VERSION,
        "query": {
            **spec.query.query_metadata(),
            "truncated": len(rows) > spec.query.limit,
        },
        "comparison": spec.previous.as_dict() if spec.previous else None,
        "totals": _independent_totals(spec.query),
        "rows": output,
        "diagnostic_notice": (
            "Indicators are behavioral diagnostics, not bot classifications. "
            "Cookieless counting may merge browsers sharing a masked network."
        ),
    }


class QueryLimitError(RuntimeError):
    """The bounded query cannot return a correct result within server limits."""


def _limit_rows(spec: QuerySpec, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    if spec.operation == "totals":
        return rows[:1], False
    if spec.operation == "breakdown":
        return rows[: spec.limit], len(rows) > spec.limit
    if not spec.dimensions:
        return rows, False

    ranking_metric = spec.metrics[0]
    totals: dict[tuple[object, ...], float] = {}
    for row in rows:
        key = _dimension_key(row, spec.dimensions)
        value = row.get(ranking_metric)
        totals[key] = totals.get(key, 0.0) + (float(value) if value is not None else 0.0)
    ranked = sorted(
        totals,
        key=lambda key: (-totals[key], tuple(str(value or "") for value in key)),
    )
    selected_keys = set(ranked[: spec.limit])
    return (
        [row for row in rows if _dimension_key(row, spec.dimensions) in selected_keys],
        len(ranked) > spec.limit,
    )


def _independent_totals(spec: QuerySpec) -> dict[str, Any]:
    total_spec = replace(spec, operation="totals", dimensions=(), granularity=None, limit=1)
    rows, _ = aggregate(total_spec, hard_limit=1)
    if not rows:
        return {metric: 0 for metric in spec.metrics}
    return {metric: rows[0].get(metric) for metric in spec.metrics} | (
        {"unavailable_reasons": rows[0]["unavailable_reasons"]}
        if rows[0].get("unavailable_reasons")
        else {}
    )


def _metric_total(spec: QuerySpec, date_range: ResolvedRange, metric: str) -> Any:
    total_spec = replace(
        spec,
        operation="totals",
        dimensions=(),
        granularity=None,
        metrics=(metric,),
        date_range=date_range,
        limit=1,
    )
    rows, _ = aggregate(total_spec, hard_limit=1)
    return rows[0].get(metric) if rows else 0


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def _metric_metadata(metrics: tuple[str, ...]) -> dict[str, dict[str, object]]:
    return {metric: dict(METRICS[metric]) for metric in metrics}


def _dimension_key(row: dict[str, Any], dimensions: tuple[str, ...]) -> tuple[object, ...]:
    return tuple(row.get(dimension) for dimension in dimensions)


def _subtract(left: Any, right: Any) -> Any:
    if left is None or right is None:
        return None
    return left - right


def _reason(row: dict[str, Any], metric: str) -> str:
    return row.get("unavailable_reasons", {}).get(metric, "metric_unavailable")


def _keep_comparison_row(row: dict[str, Any], spec: CompareSpec) -> bool:
    current = row.get("current")
    previous = row.get("previous")
    absolute = row.get("absolute_change")
    if current is not None and current < spec.minimum_current:
        return False
    if previous is not None and previous < spec.minimum_previous:
        return False
    if (current or 0) + (previous or 0) < spec.minimum_total:
        return False
    if spec.direction == "gains" and (absolute is None or absolute <= 0):
        return False
    return not (spec.direction == "losses" and (absolute is None or absolute >= 0))


def _ratio(numerator: Any, denominator: Any) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(numerator / denominator, 6)


def _percent(numerator: Any, denominator: Any) -> float | None:
    value = _ratio(numerator, denominator)
    return round(value * 100, 6) if value is not None else None


def _dominance(spec: QuerySpec, secondary: str) -> dict[tuple[object, ...], tuple[Any, float]]:
    if secondary in spec.dimensions or len(spec.dimensions) >= 2:
        return {}
    dominance_spec = replace(
        spec,
        operation="breakdown",
        dimensions=(*spec.dimensions, secondary),
        metrics=("pageviews",),
        limit=500,
    )
    rows, overflow = aggregate(dominance_spec)
    if overflow:
        return {}
    totals: dict[tuple[object, ...], int] = {}
    winners: dict[tuple[object, ...], tuple[Any, int]] = {}
    for row in rows:
        key = _dimension_key(row, spec.dimensions)
        count = int(row.get("pageviews") or 0)
        totals[key] = totals.get(key, 0) + count
        if key not in winners or count > winners[key][1]:
            winners[key] = (row.get(secondary), count)
    return {
        key: (value, round(count / totals[key] * 100, 6) if totals[key] else 0.0)
        for key, (value, count) in winners.items()
    }


def _indicators(row: dict[str, Any], thresholds: dict[str, float]) -> list[dict[str, Any]]:
    if (row.get("pageviews") or 0) < thresholds["minimum_pageviews"]:
        return []
    candidates = [
        ("high_pages_per_visitor", row.get("pages_per_daily_unique_visitor"), ">="),
        ("high_one_page_share", row.get("one_page_visit_share"), ">="),
        ("single_browser_concentration", row.get("dominant_browser_share"), ">="),
        ("single_device_concentration", row.get("dominant_device_share"), ">="),
        ("sudden_volume_change", abs(row.get("pageview_change_percent") or 0), ">="),
    ]
    return [
        {
            "name": name,
            "measured_value": measured,
            "operator": operator,
            "threshold": thresholds[name],
        }
        for name, measured, operator in candidates
        if measured is not None and measured >= thresholds[name]
    ]
