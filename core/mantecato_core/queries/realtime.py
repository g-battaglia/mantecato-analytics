"""Realtime queries — aggregate pageview counts for the last few minutes.

Privacy-first: only pageview counts and URL paths. No session or visitor tracking.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.mantecato_core.database import raw_query


def get_active_pageviews(website_id: str) -> dict[str, Any]:
    """Aggregate pageview count in the last 5 minutes."""
    rows = raw_query(
        """SELECT COUNT(*)::bigint AS count
    FROM website_event
    WHERE website_id = {{websiteId::uuid}}
      AND created_at >= NOW() - INTERVAL '5 minutes'
      AND event_type = 1""",
        {"websiteId": website_id},
    )
    count = int(rows[0]["count"]) if rows else 0
    return {"count": count}


def get_recent_pageviews(website_id: str) -> list[dict[str, Any]]:
    """Recent pageviews in the last 30 seconds for the live stream."""
    rows = raw_query(
        """SELECT
      created_at,
      url_path,
      country,
      browser
    FROM website_event
    WHERE website_id = {{websiteId::uuid}}
      AND created_at >= NOW() - INTERVAL '30 seconds'
      AND event_type = 1
    ORDER BY created_at DESC
    LIMIT 50""",
        {"websiteId": website_id},
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


def get_current_pages(website_id: str) -> list[dict[str, Any]]:
    """Pages currently being viewed (5-minute window)."""
    rows = raw_query(
        """SELECT
      url_path,
      COUNT(*)::bigint AS pageviews
    FROM website_event
    WHERE website_id = {{websiteId::uuid}}
      AND created_at >= NOW() - INTERVAL '5 minutes'
      AND event_type = 1
    GROUP BY url_path
    ORDER BY pageviews DESC
    LIMIT 20""",
        {"websiteId": website_id},
    )

    return [
        {
            "urlPath": r["url_path"],
            "pageviews": int(r["pageviews"] or 0),
        }
        for r in rows
    ]


# Backward-compatible aliases
get_active_visitors = get_active_pageviews
get_recent_events = get_recent_pageviews
