"""Realtime queries — aggregate pageview counts for the last few minutes.

Privacy-first: only pageview counts and URL paths. No session or visitor tracking.

Every query takes the same ``filters`` as the rest of the dashboard, so the bot
filter (and any content/geo filter) applies downstream and **consistently**: with
the bot filter **off** bots are included — matching the site KPIs at read time —
and **on** they are excluded. No metric silently hard-drops bots.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import Filter, prepare_filters


def get_active_pageviews(
    website_id: str, filters: list[Filter] | None = None
) -> dict[str, Any]:
    """Realtime activity in the last 5 minutes: pageviews + distinct visitors online.

    ``visitors`` counts distinct window digests seen in the last 5 minutes — the
    "visitors online" figure. The bot/content filter applies downstream like every
    other metric (off ⇒ bots included, on ⇒ bots excluded), so realtime stays
    consistent with the site KPIs instead of hard-dropping bots unconditionally.
    """
    filter_where, filter_params, _ = prepare_filters(filters)
    rows = raw_query(
        """SELECT
      COUNT(*)::bigint AS count,
      COUNT(DISTINCT we.visitor_key)::bigint AS visitors
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at >= NOW() - INTERVAL '5 minutes'
      AND we.event_type = 1
      """
        + filter_where,
        {"websiteId": website_id, **filter_params},
    )
    count = int(rows[0]["count"]) if rows else 0
    visitors = int(rows[0]["visitors"] or 0) if rows else 0
    return {"count": count, "visitors": visitors}


def get_recent_pageviews(
    website_id: str, filters: list[Filter] | None = None
) -> list[dict[str, Any]]:
    """Recent pageviews in the last 30 seconds for the live stream."""
    filter_where, filter_params, _ = prepare_filters(filters)
    rows = raw_query(
        """SELECT
      we.created_at,
      we.url_path,
      we.country,
      we.browser
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at >= NOW() - INTERVAL '30 seconds'
      AND we.event_type = 1
      """
        + filter_where
        + """
    ORDER BY we.created_at DESC
    LIMIT 50""",
        {"websiteId": website_id, **filter_params},
    )

    return [
        {
            "createdAt": r["created_at"].isoformat()
            if isinstance(r["created_at"], datetime)
            else str(r["created_at"]),
            "urlPath": r["url_path"],
            "country": r["country"],
            "browser": r["browser"],
        }
        for r in rows
    ]


def get_current_pages(
    website_id: str, filters: list[Filter] | None = None
) -> list[dict[str, Any]]:
    """Pages currently being viewed (5-minute window)."""
    filter_where, filter_params, _ = prepare_filters(filters)
    rows = raw_query(
        """SELECT
      we.url_path,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at >= NOW() - INTERVAL '5 minutes'
      AND we.event_type = 1
      """
        + filter_where
        + """
    GROUP BY we.url_path
    ORDER BY pageviews DESC
    LIMIT 20""",
        {"websiteId": website_id, **filter_params},
    )

    return [
        {
            "urlPath": r["url_path"],
            "pageviews": int(r["pageviews"] or 0),
        }
        for r in rows
    ]
