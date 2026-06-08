"""Realtime queries — aggregate pageview counts for the last few minutes.

Privacy-first: only pageview counts and URL paths. No session or visitor tracking.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.db.models import Count
from django.utils import timezone

from core.mantecato_core.database import raw_query
from core.mantecato_core.queries.orm_fallbacks import should_use_orm_fallback


def get_active_pageviews(website_id: str) -> dict[str, Any]:
    """Aggregate pageview count in the last 5 minutes."""
    if should_use_orm_fallback():
        from apps.core.models import WebsiteEvent

        count = WebsiteEvent.objects.filter(
            website_id=website_id,
            created_at__gte=timezone.now() - timedelta(minutes=5),
            event_type=1,
        ).count()
        return {"count": count}

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
    if should_use_orm_fallback():
        from apps.core.models import WebsiteEvent

        rows = WebsiteEvent.objects.filter(
            website_id=website_id,
            created_at__gte=timezone.now() - timedelta(seconds=30),
            event_type=1,
        ).order_by("-created_at")[:50]
        return [
            {
                "createdAt": row.created_at.isoformat(),
                "urlPath": row.url_path,
                "country": row.country,
                "browser": row.browser,
            }
            for row in rows
        ]

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
    if should_use_orm_fallback():
        from apps.core.models import WebsiteEvent

        rows = (
            WebsiteEvent.objects.filter(
                website_id=website_id,
                created_at__gte=timezone.now() - timedelta(minutes=5),
                event_type=1,
            )
            .values("url_path")
            .annotate(pageviews=Count("event_id"))
            .order_by("-pageviews", "url_path")[:20]
        )
        return [
            {
                "urlPath": row["url_path"],
                "pageviews": int(row["pageviews"] or 0),
            }
            for row in rows
        ]

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
