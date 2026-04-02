"""
Filter value autocomplete — distinct values for a given column.
Ported verbatim from src/queries/filter-values.ts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..database import raw_query
from ..filters import SESSION_COLUMNS

VALID_COLUMNS: set[str] = {
    "url_path",
    "page_title",
    "hostname",
    "referrer_domain",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "event_name",
    "tag",
    "browser",
    "os",
    "device",
    "country",
    "region",
    "city",
    "language",
    "screen",
}


async def get_filter_values(
    website_id: str,
    column: str,
    start_date: datetime,
    end_date: datetime,
    search: str | None = None,
    limit: int = 50,
) -> list[str]:
    """Get distinct values for a filter column, scoped to website + date range."""
    if column not in VALID_COLUMNS:
        return []

    is_session_col = column in SESSION_COLUMNS
    params: dict[str, Any] = {
        "websiteId": website_id,
        "startDate": start_date,
        "endDate": end_date,
    }

    prefix = "s" if is_session_col else "we"

    search_clause = ""
    if search:
        search_clause = f"AND {prefix}.{column} ILIKE {{{{search}}}}"
        params["search"] = f"%{search}%"

    if is_session_col:
        rows = await raw_query(
            f"""SELECT DISTINCT s.{column} AS value
         FROM website_event we
         JOIN session s ON s.session_id = we.session_id
         WHERE we.website_id = {{{{websiteId::uuid}}}}
           AND we.created_at BETWEEN {{{{startDate::timestamptz}}}} AND {{{{endDate::timestamptz}}}}
           AND s.{column} IS NOT NULL
           AND s.{column} != ''
           {search_clause}
         ORDER BY value
         LIMIT {limit}""",
            params,
        )
    else:
        rows = await raw_query(
            f"""SELECT DISTINCT we.{column} AS value
         FROM website_event we
         WHERE we.website_id = {{{{websiteId::uuid}}}}
           AND we.created_at BETWEEN {{{{startDate::timestamptz}}}} AND {{{{endDate::timestamptz}}}}
           AND we.{column} IS NOT NULL
           AND we.{column} != ''
           {search_clause}
         ORDER BY value
         LIMIT {limit}""",
            params,
        )

    return [row["value"] for row in rows]
