"""Content-group queries — pageview metrics grouped by site-declared labels.

A content group is a label the *site* attaches to a page through the tracker
(``data-groups="topic:guides,format:tutorial"``). One page can declare several,
so per-group views overlap and do not sum to the site total.

``namespace`` narrows the dimension values themselves (the text before the first
``:``). This is deliberately separate from analytics filters, which narrow the
source pageviews and then expose every group those rows carry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import prepare_filters

if TYPE_CHECKING:
    from datetime import datetime

    from core.mantecato_core.filters import Filter

GROUP_SORTS = frozenset({"views", "pages", "name"})
GROUP_LIMITS = frozenset({20, 50, 100})


def normalise_group_options(
    *,
    namespace: str | None = None,
    search: str | None = None,
    min_views: int = 0,
    sort: str = "views",
    limit: int = 100,
    preset_limits_only: bool = False,
) -> dict[str, Any]:
    """Validate group controls and optionally restrict rows to public presets."""
    clean_namespace = namespace.strip().lower()[:32] or None if isinstance(namespace, str) else None
    clean_search = search.strip()[:96] or None if isinstance(search, str) else None
    clean_sort = sort if isinstance(sort, str) and sort in GROUP_SORTS else "views"
    try:
        clean_min_views = min(max(0, int(min_views)), 9_223_372_036_854_775_807)
    except (TypeError, ValueError, OverflowError):
        clean_min_views = 0
    try:
        wanted_limit = int(limit)
    except (TypeError, ValueError, OverflowError):
        wanted_limit = 100
    # Query/CLI callers may deliberately ask for any small result set. Public
    # service callers expose the stable 20/50/100 choices and reject hand-edited
    # values rather than running unexpectedly broad queries.
    clean_limit = (
        wanted_limit
        if preset_limits_only and wanted_limit in GROUP_LIMITS
        else 100
        if preset_limits_only
        else max(1, min(wanted_limit, 1000))
    )
    return {
        "namespace": clean_namespace,
        "search": clean_search,
        "min_views": clean_min_views,
        "sort": clean_sort,
        "limit": clean_limit,
    }


def _postgres_group_source() -> str:
    """Return the guarded lateral expansion shared by both group queries."""
    return """CROSS JOIN LATERAL jsonb_array_elements(
      CASE WHEN jsonb_typeof(we.content_groups) = 'array'
           THEN we.content_groups ELSE '[]'::jsonb END
    ) AS grp(elem)"""


def get_top_groups(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 100,
    filters: list[Filter] | None = None,
    *,
    namespace: str | None = None,
    search: str | None = None,
    min_views: int = 0,
    sort: str = "views",
) -> list[dict[str, Any]]:
    """Return content groups after optional dimension-level analysis controls.

    Analytics ``filters`` narrow source pageviews. ``namespace`` and ``search``
    instead narrow labels emitted by the group dimension, so asking for the
    ``tag`` namespace cannot leak co-occurring category/family rows.
    """
    options = normalise_group_options(
        namespace=namespace, search=search, min_views=min_views, sort=sort, limit=limit
    )
    filters = filters or []
    filter_where, filter_params, _ = prepare_filters(filters)
    dimension_where: list[str] = ["jsonb_typeof(grp.elem) = 'string'", "grp.elem #>> '{}' <> ''"]
    params: dict[str, Any] = {
        "websiteId": website_id,
        "startDate": start_date,
        "endDate": end_date,
        **filter_params,
    }
    if options["namespace"]:
        dimension_where.append("split_part(grp.elem #>> '{}', ':', 1) = {{groupNamespace}}")
        params["groupNamespace"] = options["namespace"]
    if options["search"]:
        dimension_where.append("grp.elem #>> '{}' ILIKE {{groupSearch}}")
        params["groupSearch"] = f"%{options['search']}%"

    order_by = {
        "views": "views DESC, 1",
        "pages": "pages DESC, views DESC, 1",
        "name": '"group" ASC',
    }[options["sort"]]
    rows = raw_query(
        f"""SELECT
      grp.elem #>> '{{}}' AS "group",
      COUNT(*)::bigint AS views,
      COUNT(DISTINCT we.url_path)::bigint AS pages
    FROM website_event we
    {_postgres_group_source()}
    WHERE we.website_id = {{{{websiteId::uuid}}}}
      AND we.created_at BETWEEN {{{{startDate::timestamptz}}}} AND {{{{endDate::timestamptz}}}}
      AND we.event_type = 1
      AND {" AND ".join(dimension_where)}
      {filter_where}
    GROUP BY 1
    HAVING COUNT(*) >= {{{{minViews::bigint}}}}
    ORDER BY {order_by}
    LIMIT {options["limit"]}""",
        {**params, "minViews": options["min_views"]},
    )
    return [
        {"group": row["group"], "views": int(row["views"] or 0), "pages": int(row["pages"] or 0)}
        for row in rows
    ]


def get_group_namespaces(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    filters: list[Filter] | None = None,
) -> list[str]:
    """Return the distinct non-empty namespaces present in the selected rows."""
    filter_where, filter_params, _ = prepare_filters(filters or [])
    rows = raw_query(
        f"""SELECT DISTINCT split_part(grp.elem #>> '{{}}', ':', 1) AS namespace
    FROM website_event we
    {_postgres_group_source()}
    WHERE we.website_id = {{{{websiteId::uuid}}}}
      AND we.created_at BETWEEN {{{{startDate::timestamptz}}}} AND {{{{endDate::timestamptz}}}}
      AND we.event_type = 1
      AND jsonb_typeof(grp.elem) = 'string'
      AND position(':' IN grp.elem #>> '{{}}') > 1
      {filter_where}
    ORDER BY 1""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )
    return [str(row["namespace"]) for row in rows if row.get("namespace")]
