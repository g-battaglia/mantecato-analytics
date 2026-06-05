"""Filter value autocomplete — distinct values for a given column.

Converted from legacy asyncpg to sync Django/psycopg3. SQL strings are unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import SESSION_COLUMNS

# Exhaustive whitelist of columns whose distinct values can be queried.
# This is the security boundary: only these column names are ever
# interpolated into SQL strings.  Adding a column here also makes it
# available for filter autocomplete in the dashboard UI.
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


def get_filter_values(
    website_id: str,
    column: str,
    start_date: datetime,
    end_date: datetime,
    search: str | None = None,
    limit: int = 50,
) -> list[str]:
    """Retrieve distinct values for a given column, for filter autocomplete.

    Powers the typeahead / autocomplete dropdowns in the dashboard
    filter bar.  When a user starts typing a filter value, this
    function returns matching distinct values from the database.

    The function automatically determines whether the requested column
    lives on the ``website_event`` table or the ``session`` table
    (using the ``SESSION_COLUMNS`` set from the filters module) and
    generates the appropriate query.  Session-column queries include a
    JOIN to the ``session`` table.

    When a ``search`` term is provided, an ``ILIKE`` clause is added
    for case-insensitive substring matching (e.g. typing "chr" matches
    "Chrome").  The search term is wrapped with ``%`` wildcards.

    Args:
        website_id: UUID of the tracked website.
        column: Name of the column to retrieve distinct values for.
            Must be in ``VALID_COLUMNS``.
        start_date: Inclusive start of the time window to search.
        end_date: Exclusive end of the time window.
        search: Optional substring to filter values by (case-insensitive).
        limit: Maximum number of values to return (default 50).

    Returns:
        List of distinct non-empty string values, sorted alphabetically.
        Returns an empty list if ``column`` is not in ``VALID_COLUMNS``.
    """
    # Whitelist validation: column names are interpolated into SQL.
    if column not in VALID_COLUMNS:
        return []

    # Determine which table the column belongs to: session columns (browser,
    # os, country, etc.) require a JOIN, event columns are on website_event.
    is_session_col = column in SESSION_COLUMNS
    params: dict[str, Any] = {
        "websiteId": website_id,
        "startDate": start_date,
        "endDate": end_date,
    }

    prefix = "s" if is_session_col else "we"

    # Optional case-insensitive substring search for typeahead filtering.
    search_clause = ""
    if search:
        search_clause = f"AND {prefix}.{column} ILIKE {{{{search}}}}"
        params["search"] = f"%{search}%"

    if is_session_col:
        rows = raw_query(
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
        rows = raw_query(
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
