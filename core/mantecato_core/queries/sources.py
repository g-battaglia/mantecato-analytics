"""Traffic-source breakdown queries — aggregate pageviews by referrer domain.

Privacy-first: only the referrer **domain** is ever stored (never the full URL,
its query string, or any UTM/click ID — see :mod:`apps.tracker.services`). Direct
traffic (no referrer) and same-site referrals are recorded as ``NULL`` and so are
naturally excluded from this breakdown.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import Filter, prepare_filters
from core.mantecato_core.queries.orm_fallbacks import (
    count_by_field,
    pageview_queryset,
    should_use_orm_fallback,
)


def get_referrer_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 50,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Aggregate pageview counts by referrer domain (top traffic sources)."""
    if should_use_orm_fallback():
        rows = count_by_field(
            pageview_queryset(website_id, start_date, end_date, filters),
            "referrer_domain",
            "pageviews",
            limit,
        )
        total = sum(int(row["pageviews"] or 0) for row in rows)
        return [
            {
                "referrer": row["value"],
                "pageviews": int(row["pageviews"] or 0),
                "percentage": round((int(row["pageviews"] or 0) / total) * 100, 1)
                if total > 0
                else 0,
            }
            for row in rows
        ]

    filters = filters or []
    filter_where, filter_params, _ = prepare_filters(filters)

    params: dict[str, Any] = {
        "websiteId": website_id,
        "startDate": start_date,
        "endDate": end_date,
        **filter_params,
    }

    rows = raw_query(
        """SELECT
      we.referrer_domain AS referrer,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    WHERE we.website_id = {websiteId::uuid}
      AND we.created_at BETWEEN {startDate::timestamptz} AND {endDate::timestamptz}
      AND we.event_type = 1
      AND we.referrer_domain IS NOT NULL
      AND we.referrer_domain != ''
      """ + filter_where + """
    GROUP BY we.referrer_domain
    ORDER BY pageviews DESC
    LIMIT """ + str(limit),
        params,
    )

    total = sum(int(r["pageviews"] or 0) for r in rows)

    return [
        {
            "referrer": row["referrer"],
            "pageviews": int(row["pageviews"] or 0),
            "percentage": round((int(row["pageviews"] or 0) / total) * 100, 1) if total > 0 else 0,
        }
        for row in rows
    ]
