"""Realtime queries — active visitors, recent events, and current pages.

Converted from legacy asyncpg to sync Django/psycopg3. SQL strings are unchanged.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.mantecato_core.database import raw_query


def get_active_visitors(
    website_id: str,
) -> dict[str, Any]:
    """Active visitors in the last 5 minutes with their last-seen page."""
    rows = raw_query(
        """SELECT DISTINCT ON (we.session_id)
      we.session_id,
      we.url_path,
      s.country,
      s.city,
      s.browser,
      s.os,
      we.created_at AS last_seen
    FROM website_event we
    JOIN session s ON s.session_id = we.session_id
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at >= NOW() - INTERVAL '5 minutes'
    ORDER BY we.session_id, we.created_at DESC""",
        {"websiteId": website_id},
    )

    visitors = [
        {
            "sessionId": r["session_id"],
            "urlPath": r["url_path"],
            "country": r["country"],
            "city": r["city"],
            "browser": r["browser"],
            "os": r["os"],
            "lastSeen": r["last_seen"].isoformat()
            if isinstance(r["last_seen"], datetime)
            else str(r["last_seen"]),
        }
        for r in rows
    ]

    return {"count": len(visitors), "visitors": visitors}


def get_recent_events(
    website_id: str,
) -> list[dict[str, Any]]:
    """Events in the last 30 seconds for the live stream."""
    rows = raw_query(
        """SELECT
      we.created_at,
      we.url_path,
      we.event_type,
      we.event_name,
      s.country,
      s.browser
    FROM website_event we
    JOIN session s ON s.session_id = we.session_id
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at >= NOW() - INTERVAL '30 seconds'
    ORDER BY we.created_at DESC
    LIMIT 50""",
        {"websiteId": website_id},
    )

    return [
        {
            "createdAt": r["created_at"].isoformat()
            if isinstance(r["created_at"], datetime)
            else str(r["created_at"]),
            "urlPath": r["url_path"],
            "eventType": r["event_type"],
            "eventName": r["event_name"],
            "country": r["country"],
            "browser": r["browser"],
        }
        for r in rows
    ]


def get_current_pages(
    website_id: str,
) -> list[dict[str, Any]]:
    """Pages currently being viewed (5-minute window)."""
    rows = raw_query(
        """SELECT
      url_path,
      COUNT(DISTINCT session_id)::bigint AS visitors
    FROM website_event
    WHERE website_id = {{websiteId::uuid}}
      AND created_at >= NOW() - INTERVAL '5 minutes'
      AND event_type = 1
    GROUP BY url_path
    ORDER BY visitors DESC
    LIMIT 20""",
        {"websiteId": website_id},
    )

    return [
        {
            "urlPath": r["url_path"],
            "visitors": int(r["visitors"] or 0),
        }
        for r in rows
    ]
