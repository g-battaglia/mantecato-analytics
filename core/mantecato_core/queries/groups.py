"""Content-group queries — pageview metrics grouped by site-declared labels.

A content group is a label the *site* attaches to a page through the tracker
tag (``data-groups="guides,pricing"``). It is page metadata, like the title, so
grouping by it stays inside the same aggregate, cookieless model as every other
breakdown here.

Sections group by URL prefix, which only works when the URL carries the
taxonomy. Sites whose article URLs are flat (``/p/<slug>``) get nothing from
that; content groups let them break the same traffic down by whatever dimension
they actually care about.

One page can declare several groups, so a pageview counts once in each of them:
**the per-group views do not sum to the site total**, exactly like a tag cloud.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import prepare_filters
from core.mantecato_core.queries.orm_fallbacks import (
    pageview_queryset,
    should_use_orm_fallback,
    top_groups_from_qs,
)

if TYPE_CHECKING:
    from datetime import datetime

    from core.mantecato_core.filters import Filter


def get_top_groups(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 100,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Return the most-viewed content groups.

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        limit: Maximum number of group rows to return.
        filters: Optional column filters to narrow the dataset.

    Returns:
        List of dicts with ``group``, ``views`` and ``pages`` (distinct URLs
        carrying the label), sorted by views descending. Pageviews that declare
        no group are absent — they belong to no group, rather than to an
        "(unlabelled)" bucket that would read as a real section.
    """
    if should_use_orm_fallback():
        return top_groups_from_qs(
            pageview_queryset(website_id, start_date, end_date, filters), limit
        )

    filters = filters or []
    filter_where, filter_params, _ = prepare_filters(filters)

    rows = raw_query(
        f"""SELECT
      grp.elem #>> '{{}}' AS "group",
      COUNT(*)::bigint AS views,
      COUNT(DISTINCT we.url_path)::bigint AS pages
    FROM website_event we
    CROSS JOIN LATERAL jsonb_array_elements(
      -- The column is an unconstrained JSONField, so a scalar can reach here.
      -- The guard has to live inside the lateral: a jsonb_typeof() predicate in
      -- WHERE is not ordered before the FROM clause that expands the value, so
      -- the expansion would raise on a non-array and abort the whole query.
      -- Mirrors get_filter_values().
      CASE WHEN jsonb_typeof(we.content_groups) = 'array'
           THEN we.content_groups ELSE '[]'::jsonb END
    ) AS grp(elem)
    WHERE we.website_id = {{{{websiteId::uuid}}}}
      AND we.created_at BETWEEN {{{{startDate::timestamptz}}}} AND {{{{endDate::timestamptz}}}}
      AND we.event_type = 1
      -- Only string members are labels. jsonb_array_elements_text() would
      -- stringify a number or an object into a group of its own, which the
      -- SQLite fallback and the visitor counter both refuse — the two backends
      -- would disagree on the same row.
      AND jsonb_typeof(grp.elem) = 'string'
      AND grp.elem #>> '{{}}' <> ''
      {filter_where}
    GROUP BY 1
    ORDER BY views DESC, 1
    LIMIT {int(limit)}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    return [
        {
            "group": row["group"],
            "views": int(row["views"] or 0),
            "pages": int(row["pages"] or 0),
        }
        for row in rows
    ]
