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


# ── Marketing channels ──────────────────────────────────────────────────────
# Channels are derived purely from the referrer **domain** — never from UTM tags
# or click IDs (which are never stored). Substrings are matched against the
# domain, so "google." catches google.com, google.co.uk, news.google.com, etc.

_SEARCH_ENGINES = (
    "google.", "bing.", "yahoo.", "duckduckgo.", "baidu.", "yandex.",
    "ecosia.", "ask.com", "aol.", "brave.com", "qwant.", "startpage.",
    "search.", "kagi.",
)
_SOCIAL_NETWORKS = (
    "facebook.", "fb.com", "fb.me", "instagram.", "twitter.", "x.com",
    "t.co", "linkedin.", "lnkd.in", "reddit.", "youtube.", "youtu.be",
    "pinterest.", "tiktok.", "threads.net", "mastodon.", "tumblr.",
    "whatsapp.", "telegram.", "t.me", "snapchat.", "bsky.app",
)


def classify_channel(domain: str | None) -> str:
    """Map a referrer domain to a marketing channel.

    Returns ``Direct`` (no referrer), ``Search``, ``Social``, or ``Referral``.
    """
    if not domain:
        return "Direct"
    d = domain.lower()
    if any(token in d for token in _SEARCH_ENGINES):
        return "Search"
    if any(token in d for token in _SOCIAL_NETWORKS):
        return "Social"
    return "Referral"


def _referrer_domain_counts(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    filters: list[Filter] | None,
) -> list[tuple[str | None, int]]:
    """Return ``(referrer_domain, pageviews)`` pairs, including NULL (= Direct)."""
    if should_use_orm_fallback():
        from django.db.models import Count

        rows = (
            pageview_queryset(website_id, start_date, end_date, filters)
            .values("referrer_domain")
            .annotate(total=Count("event_id"))
        )
        return [(row["referrer_domain"], int(row["total"] or 0)) for row in rows]

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
      we.referrer_domain AS domain,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    WHERE we.website_id = {websiteId::uuid}
      AND we.created_at BETWEEN {startDate::timestamptz} AND {endDate::timestamptz}
      AND we.event_type = 1
      """ + filter_where + """
    GROUP BY we.referrer_domain""",
        params,
    )
    return [(row["domain"], int(row["pageviews"] or 0)) for row in rows]


def get_channel_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Aggregate pageviews into marketing channels derived from referrer domain.

    Cookieless and UTM-free: each pageview is bucketed into Direct / Search /
    Social / Referral purely from its referrer domain. Returns rows sorted by
    pageviews descending, each with a percentage of the period total.
    """
    totals: dict[str, int] = {}
    for domain, count in _referrer_domain_counts(website_id, start_date, end_date, filters):
        channel = classify_channel(domain)
        totals[channel] = totals.get(channel, 0) + count

    total = sum(totals.values())
    rows = [
        {
            "channel": channel,
            "pageviews": count,
            "percentage": round((count / total) * 100, 1) if total > 0 else 0,
        }
        for channel, count in totals.items()
    ]
    rows.sort(key=lambda r: r["pageviews"], reverse=True)
    return rows
