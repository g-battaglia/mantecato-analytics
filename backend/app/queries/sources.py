from __future__ import annotations

from datetime import datetime
from typing import Any

from ..database import raw_query
from ..filters import Filter, build_filter_sql


async def get_referrer_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 50,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]
    session_join = (
        "JOIN session s ON s.session_id = we.session_id"
        if result["needs_session_join"]
        else ""
    )

    rows = await raw_query(
        f"""WITH visit_stats AS (
      SELECT
        we.visit_id,
        we.referrer_domain,
        COUNT(*) AS pages,
        EXTRACT(EPOCH FROM (MAX(we.created_at) - MIN(we.created_at))) AS duration
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        {filter_where}
      GROUP BY we.visit_id, we.referrer_domain
    )
    SELECT
      COALESCE(referrer_domain, '(direct)') AS referrer_domain,
      COUNT(DISTINCT visit_id)::bigint AS visitors,
      SUM(pages)::bigint AS pageviews,
      CASE WHEN COUNT(*) = 0 THEN 0
        ELSE (SUM(CASE WHEN pages = 1 THEN 1 ELSE 0 END)::float / COUNT(*) * 100)
      END AS bounce_rate,
      COALESCE(AVG(duration), 0) AS avg_duration
    FROM visit_stats
    GROUP BY referrer_domain
    ORDER BY visitors DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    return [
        {
            "referrerDomain": row["referrer_domain"],
            "visitors": int(row["visitors"] or 0),
            "pageviews": int(row["pageviews"] or 0),
            "bounceRate": row["bounce_rate"] or 0,
            "avgDuration": row["avg_duration"] or 0,
        }
        for row in rows
    ]


async def get_utm_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    group_by: str = "utm_source",
    limit: int = 50,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    valid_fields = ["utm_source", "utm_medium", "utm_campaign"]
    if group_by not in valid_fields:
        return []
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]
    session_join = (
        "JOIN session s ON s.session_id = we.session_id"
        if result["needs_session_join"]
        else ""
    )

    rows = await raw_query(
        f"""SELECT
      we.utm_source,
      we.utm_medium,
      we.utm_campaign,
      COUNT(DISTINCT we.session_id)::bigint AS visitors,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    {session_join}
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND we.{group_by} IS NOT NULL
      {filter_where}
    GROUP BY we.utm_source, we.utm_medium, we.utm_campaign
    ORDER BY visitors DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    return [
        {
            "utmSource": row["utm_source"],
            "utmMedium": row["utm_medium"],
            "utmCampaign": row["utm_campaign"],
            "visitors": int(row["visitors"] or 0),
            "pageviews": int(row["pageviews"] or 0),
        }
        for row in rows
    ]


async def get_utm_detail_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    dimension: str,
    limit: int = 50,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    valid_dims = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"]
    if dimension not in valid_dims:
        return []
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]
    session_join = (
        "JOIN session s ON s.session_id = we.session_id"
        if result["needs_session_join"]
        else ""
    )

    rows = await raw_query(
        f"""WITH visit_stats AS (
      SELECT
        we.visit_id,
        we.{dimension} AS dim_value,
        COUNT(*) AS pages,
        EXTRACT(EPOCH FROM (MAX(we.created_at) - MIN(we.created_at))) AS duration
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        AND we.{dimension} IS NOT NULL
        {filter_where}
      GROUP BY we.visit_id, we.{dimension}
    )
    SELECT
      dim_value AS value,
      COUNT(DISTINCT visit_id)::bigint AS visitors,
      SUM(pages)::bigint AS pageviews,
      CASE WHEN COUNT(*) = 0 THEN 0
        ELSE (SUM(CASE WHEN pages = 1 THEN 1 ELSE 0 END)::float / COUNT(*) * 100)
      END AS bounce_rate,
      COALESCE(AVG(duration), 0) AS avg_duration
    FROM visit_stats
    GROUP BY dim_value
    ORDER BY visitors DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    return [
        {
            "value": row["value"],
            "visitors": int(row["visitors"] or 0),
            "pageviews": int(row["pageviews"] or 0),
            "bounceRate": row["bounce_rate"] or 0,
            "avgDuration": row["avg_duration"] or 0,
        }
        for row in rows
    ]


async def get_channel_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]
    session_join = (
        "JOIN session s ON s.session_id = we.session_id"
        if result["needs_session_join"]
        else ""
    )

    rows = await raw_query(
        f"""WITH visit_stats AS (
      SELECT
        we.visit_id,
        CASE
          WHEN we.utm_medium IN ('cpc', 'ppc', 'paid', 'paidsearch', 'paid-search') THEN 'Paid Search'
          WHEN we.utm_medium IN ('display', 'banner', 'cpm') THEN 'Display'
          WHEN we.utm_medium IN ('social', 'social-media', 'sm') THEN 'Paid Social'
          WHEN we.utm_medium = 'email' THEN 'Email'
          WHEN we.utm_medium = 'affiliate' THEN 'Affiliate'
          WHEN we.utm_source IN ('google', 'bing', 'yahoo', 'duckduckgo', 'baidu', 'yandex')
            AND (we.utm_medium IS NULL OR we.utm_medium = 'organic') THEN 'Organic Search'
          WHEN we.referrer_domain IN ('t.co', 'facebook.com', 'l.facebook.com', 'instagram.com',
            'linkedin.com', 'lnkd.in', 'reddit.com', 'youtube.com', 'tiktok.com', 'pinterest.com',
            'x.com', 'threads.net', 'mastodon.social') THEN 'Organic Social'
          WHEN we.referrer_domain IS NOT NULL AND we.referrer_domain != '' THEN 'Referral'
          ELSE 'Direct'
        END AS channel,
        COUNT(*) AS pages,
        EXTRACT(EPOCH FROM (MAX(we.created_at) - MIN(we.created_at))) AS duration
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        {filter_where}
      GROUP BY we.visit_id, channel
    )
    SELECT
      channel,
      COUNT(DISTINCT visit_id)::bigint AS visitors,
      SUM(pages)::bigint AS pageviews,
      CASE WHEN COUNT(*) = 0 THEN 0
        ELSE (SUM(CASE WHEN pages = 1 THEN 1 ELSE 0 END)::float / COUNT(*) * 100)
      END AS bounce_rate,
      COALESCE(AVG(duration), 0) AS avg_duration
    FROM visit_stats
    GROUP BY channel
    ORDER BY visitors DESC""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    return [
        {
            "channel": row["channel"],
            "visitors": int(row["visitors"] or 0),
            "pageviews": int(row["pageviews"] or 0),
            "bounceRate": row["bounce_rate"] or 0,
            "avgDuration": row["avg_duration"] or 0,
        }
        for row in rows
    ]


async def get_click_id_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]
    session_join = (
        "JOIN session s ON s.session_id = we.session_id"
        if result["needs_session_join"]
        else ""
    )

    rows = await raw_query(
        f"""WITH click_ids AS (
      SELECT
        we.visit_id,
        CASE
          WHEN we.gclid IS NOT NULL THEN 'Google Ads (gclid)'
          WHEN we.fbclid IS NOT NULL THEN 'Meta Ads (fbclid)'
          WHEN we.msclkid IS NOT NULL THEN 'Microsoft Ads (msclkid)'
          WHEN we.ttclid IS NOT NULL THEN 'TikTok Ads (ttclid)'
          WHEN we.twclid IS NOT NULL THEN 'Twitter/X Ads (twclid)'
          WHEN we.li_fat_id IS NOT NULL THEN 'LinkedIn Ads (li_fat_id)'
        END AS platform,
        COUNT(*) AS pages,
        EXTRACT(EPOCH FROM (MAX(we.created_at) - MIN(we.created_at))) AS duration
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        AND (we.gclid IS NOT NULL OR we.fbclid IS NOT NULL OR we.msclkid IS NOT NULL
             OR we.ttclid IS NOT NULL OR we.twclid IS NOT NULL OR we.li_fat_id IS NOT NULL)
        {filter_where}
      GROUP BY we.visit_id, platform
    )
    SELECT
      platform,
      COUNT(DISTINCT visit_id)::bigint AS visitors,
      SUM(pages)::bigint AS pageviews,
      CASE WHEN COUNT(*) = 0 THEN 0
        ELSE (SUM(CASE WHEN pages = 1 THEN 1 ELSE 0 END)::float / COUNT(*) * 100)
      END AS bounce_rate,
      COALESCE(AVG(duration), 0) AS avg_duration
    FROM click_ids
    WHERE platform IS NOT NULL
    GROUP BY platform
    ORDER BY visitors DESC""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    return [
        {
            "platform": row["platform"],
            "visitors": int(row["visitors"] or 0),
            "pageviews": int(row["pageviews"] or 0),
            "bounceRate": row["bounce_rate"] or 0,
            "avgDuration": row["avg_duration"] or 0,
        }
        for row in rows
    ]


async def get_referrer_pages(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    referrer_domain: str,
    limit: int = 20,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]
    session_join = (
        "JOIN session s ON s.session_id = we.session_id"
        if result["needs_session_join"]
        else ""
    )

    is_direct = referrer_domain == "(direct)"
    referrer_condition = (
        "AND we.referrer_domain IS NULL"
        if is_direct
        else "AND we.referrer_domain = {{referrerDomain}}"
    )
    extra_params: dict[str, Any] = {}
    if not is_direct:
        extra_params["referrerDomain"] = referrer_domain

    rows = await raw_query(
        f"""SELECT
      we.url_path,
      COUNT(DISTINCT we.session_id)::bigint AS visitors,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    {session_join}
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      {referrer_condition}
      {filter_where}
    GROUP BY we.url_path
    ORDER BY pageviews DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **extra_params,
            **filter_params,
        },
    )

    return [
        {
            "urlPath": row["url_path"],
            "visitors": int(row["visitors"] or 0),
            "pageviews": int(row["pageviews"] or 0),
        }
        for row in rows
    ]


async def get_hostname_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 50,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]
    session_join = (
        "JOIN session s ON s.session_id = we.session_id"
        if result["needs_session_join"]
        else ""
    )

    rows = await raw_query(
        f"""WITH visit_stats AS (
      SELECT
        we.visit_id,
        we.hostname,
        COUNT(*) AS pages,
        EXTRACT(EPOCH FROM (MAX(we.created_at) - MIN(we.created_at))) AS duration
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        AND we.hostname IS NOT NULL AND we.hostname != ''
        {filter_where}
      GROUP BY we.visit_id, we.hostname
    )
    SELECT
      hostname,
      COUNT(DISTINCT visit_id)::bigint AS visitors,
      SUM(pages)::bigint AS pageviews,
      CASE WHEN COUNT(*) = 0 THEN 0
        ELSE (SUM(CASE WHEN pages = 1 THEN 1 ELSE 0 END)::float / COUNT(*) * 100)
      END AS bounce_rate,
      COALESCE(AVG(duration), 0) AS avg_duration
    FROM visit_stats
    GROUP BY hostname
    ORDER BY visitors DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    return [
        {
            "hostname": row["hostname"],
            "visitors": int(row["visitors"] or 0),
            "pageviews": int(row["pageviews"] or 0),
            "bounceRate": row["bounce_rate"] or 0,
            "avgDuration": row["avg_duration"] or 0,
        }
        for row in rows
    ]
