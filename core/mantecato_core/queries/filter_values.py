"""Filter values — distinct column values for the filter typeahead.

Privacy-first: queries website_event directly, no session join needed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from core.mantecato_core.database import raw_query

# Columns that can be filtered and whose distinct values power the typeahead.
_VALID_COLUMNS = {
    "url_path": "we.url_path",
    "page_title": "we.page_title",
    "hostname": "we.hostname",
    "browser": "we.browser",
    "os": "we.os",
    "device": "we.device",
    "country": "we.country",
}


def get_filter_values(
    website_id: str,
    column: str,
    start_date: datetime,
    end_date: datetime,
    search: str | None = None,
    limit: int = 20,
) -> list[str]:
    """Return distinct values for a column, optionally filtered by a search substring."""
    col_expr = _VALID_COLUMNS.get(column)
    if not col_expr:
        return []

    where_extra = ""
    params: dict[str, Any] = {
        "websiteId": website_id,
        "startDate": start_date,
        "endDate": end_date,
    }
    if search:
        where_extra = f"AND {col_expr} ILIKE {{{{search}}}}"
        params["search"] = f"%{search}%"

    rows = raw_query(
        f"""SELECT DISTINCT {col_expr} AS value
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND {col_expr} IS NOT NULL
      AND {col_expr} != ''
      {where_extra}
    ORDER BY 1
    LIMIT {limit}""",
        params,
    )
    return [str(r["value"]) for r in rows]
