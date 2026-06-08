"""Estimated unique visitor queries from anonymous aggregate sketches."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from apps.core.models import VisitorSketch
from core.mantecato_core.visitor_estimation import bucket_hour, estimate, merge_registers


def estimate_unique_visitors(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    *,
    scope: str = "site",
    scope_value: str = "",
) -> int | None:
    """Estimate unique visitors for one scope from hourly sketches."""
    values = estimate_unique_visitors_by_scope(
        website_id,
        start_date,
        end_date,
        scope=scope,
        scope_values=[scope_value],
    )
    return values.get(scope_value)


def estimate_unique_visitors_by_scope(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    *,
    scope: str,
    scope_values: list[str],
) -> dict[str, int]:
    """Estimate unique visitors for several scope values.

    Returns an empty mapping when no sketches exist yet.
    """
    if not scope_values:
        return {}
    start_bucket = bucket_hour(start_date)
    end_bucket = bucket_hour(end_date)
    rows = VisitorSketch.objects.filter(
        website_id=website_id,
        scope=scope,
        scope_value__in=scope_values,
        bucket_start__gte=start_bucket,
        bucket_start__lte=end_bucket,
    ).values("scope_value", "registers")

    grouped: dict[str, list[Any]] = {value: [] for value in scope_values}
    for row in rows.iterator():
        grouped.setdefault(row["scope_value"], []).append(row["registers"])
    return {
        value: estimate(merge_registers(registers))
        for value, registers in grouped.items()
        if registers
    }
