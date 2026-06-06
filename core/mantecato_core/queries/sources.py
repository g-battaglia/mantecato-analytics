"""Traffic source queries — referrers, UTM, channels, click IDs, hostnames.

Converted from legacy asyncpg to sync Django/psycopg3. SQL strings are unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import Filter, prepare_filters

# SQL fragment reused across this module to strip the "www." prefix from
# referrer domains, so "www.example.com" and "example.com" collapse into
# a single bucket.
_NORM_REFERRER = "REGEXP_REPLACE(we.referrer_domain, '^www\\.', '')"

# Companion fragment that normalises the request hostname the same way,
# used to drop self-referrers (rows where the user navigated within the
# same site) from referrer-centric aggregates -- matches Umami's behaviour.
_NORM_HOSTNAME = "REGEXP_REPLACE(we.hostname, '^www\\.', '')"

# WHERE-clause snippet that filters out self-referrers.  ``COALESCE`` on
# the hostname side guards against rows where ``hostname`` is NULL (very
# old events): in that case we keep the row instead of silently dropping it.
_EXCLUDE_SELF_REFERRER = f"AND {_NORM_REFERRER} != COALESCE({_NORM_HOSTNAME}, '')"


def get_referrer_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 50,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Compute visitor, pageview, bounce rate, and duration metrics grouped by referrer domain.

    Normalizes referrer URLs to domain-only (stripping the ``www.``
    prefix) and aggregates metrics per unique referrer.  Visits with
    no referrer header are reported as ``(direct)``.

    The query uses a two-phase CTE approach: ``visit_stats`` first
    computes per-visit aggregates (page count, duration) so that the
    outer SELECT can derive bounce rate and average duration without
    double-counting multi-page visits.

    A session JOIN is conditionally included when device/geo filters
    are active, because referrer data lives on the ``website_event``
    row while device and geo data live on the ``session`` row.

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        limit: Maximum number of referrer rows to return (default 50).
        filters: Optional list of column filters to narrow the dataset.

    Returns:
        List of dicts, each containing:
        - ``referrerDomain`` (str): The normalized domain, or ``(direct)``.
        - ``visitors`` (int): Unique visitor (visit_id) count.
        - ``pageviews`` (int): Total pageview count across all visits.
        - ``bounceRate`` (float): Percentage of single-page visits.
        - ``avgDuration`` (float): Average visit duration in seconds.
        Sorted by visitors descending.
    """
    filters = filters or []
    filter_where, filter_params, session_join = prepare_filters(filters)

    # Phase 1 CTE: aggregate per-visit stats (page count, session duration)
    # so we can derive bounce rate and avg duration in the outer query.
    # Phase 2: group by normalized referrer domain, counting distinct visits
    # as "visitors" and summing their page counts as "pageviews".
    # Bounce rate = % of visits with exactly 1 pageview.
    #
    # Self-referrers (referrer_domain == hostname) are excluded so that
    # internal navigation does not pollute the referrer breakdown.
    # The ``(direct)`` bucket is preserved because NULL referrers never
    # match the hostname filter (NULL != hostname is always NULL in SQL),
    # but COALESCE on the hostname side keeps them when hostname is NULL.
    rows = raw_query(
        f"""WITH visit_stats AS (
      SELECT
        we.visit_id,
        {_NORM_REFERRER} AS referrer_domain,
        COUNT(*) AS pages,
        EXTRACT(EPOCH FROM (MAX(we.created_at) - MIN(we.created_at))) AS duration
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        AND (
          we.referrer_domain IS NULL
          OR {_NORM_REFERRER} != COALESCE({_NORM_HOSTNAME}, '')
        )
        {filter_where}
      GROUP BY we.visit_id, {_NORM_REFERRER}
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


def get_utm_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    group_by: str = "utm_source",
    limit: int = 50,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Aggregate visitor and pageview counts grouped by UTM parameters.

    Returns all three UTM dimensions (source, medium, campaign) for each
    row, but only includes rows where the ``group_by`` column is non-NULL.
    This lets the caller display a combined breakdown while filtering by
    the primary dimension.

    The ``group_by`` parameter is validated against a whitelist to prevent
    SQL injection, since it is interpolated directly into the query.

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        group_by: Which UTM column to require non-NULL values for.
            Must be one of ``utm_source``, ``utm_medium``, or
            ``utm_campaign``.
        limit: Maximum number of rows to return (default 50).
        filters: Optional list of column filters to narrow the dataset.

    Returns:
        List of dicts, each containing:
        - ``utmSource`` (str | None): The UTM source value.
        - ``utmMedium`` (str | None): The UTM medium value.
        - ``utmCampaign`` (str | None): The UTM campaign value.
        - ``visitors`` (int): Unique session count.
        - ``pageviews`` (int): Total pageview count.
        Sorted by visitors descending.  Returns an empty list if
        ``group_by`` is not in the allowed set.
    """
    # Whitelist check prevents SQL injection since group_by is interpolated
    # directly into the SQL string.
    valid_fields = ["utm_source", "utm_medium", "utm_campaign"]
    if group_by not in valid_fields:
        return []
    filters = filters or []
    filter_where, filter_params, session_join = prepare_filters(filters)

    rows = raw_query(
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


def get_utm_detail_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    dimension: str,
    limit: int = 50,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Compute detailed engagement metrics for a single UTM dimension.

    Unlike ``get_utm_metrics`` which returns all three main UTM columns,
    this function drills into one specific dimension (including the
    extended ``utm_content`` and ``utm_term``) and computes bounce rate
    and average visit duration alongside visitor/pageview counts.

    Uses the same two-phase CTE pattern as ``get_referrer_metrics``:
    the inner CTE aggregates per-visit stats (page count, duration),
    and the outer query groups by the chosen dimension value.

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        dimension: Which UTM column to break down.  Must be one of
            ``utm_source``, ``utm_medium``, ``utm_campaign``,
            ``utm_content``, or ``utm_term``.
        limit: Maximum number of rows to return (default 50).
        filters: Optional list of column filters to narrow the dataset.

    Returns:
        List of dicts, each containing:
        - ``value`` (str): The dimension value.
        - ``visitors`` (int): Unique visitor (visit_id) count.
        - ``pageviews`` (int): Total pageview count.
        - ``bounceRate`` (float): Percentage of single-page visits.
        - ``avgDuration`` (float): Average visit duration in seconds.
        Sorted by visitors descending.  Returns empty list if
        ``dimension`` is not in the allowed set.
    """
    # Whitelist check prevents SQL injection since dimension is interpolated
    # directly into the SQL string.
    valid_dims = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"]
    if dimension not in valid_dims:
        return []
    filters = filters or []
    filter_where, filter_params, session_join = prepare_filters(filters)

    rows = raw_query(
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


def get_channel_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Classify traffic into marketing channels and compute engagement metrics.

    Applies a deterministic waterfall of rules (checked top-to-bottom) to
    assign each visit to exactly one marketing channel:

    1. **Paid Search** -- ``utm_medium`` matches paid-search identifiers
       (cpc, ppc, paid, paidsearch, paid-search).
    2. **Display** -- ``utm_medium`` matches display ad identifiers
       (display, banner, cpm).
    3. **Paid Social** -- ``utm_medium`` is ``social`` / ``social-media`` / ``sm``.
    4. **Email** -- ``utm_medium`` is ``email``.
    5. **Affiliate** -- ``utm_medium`` is ``affiliate``.
    6. **Organic Search** -- ``utm_source`` is a known search engine AND
       ``utm_medium`` is NULL or ``organic``.
    7. **Organic Social** -- referrer domain matches a hardcoded list of
       social media domains (t.co, facebook.com, instagram.com, etc.).
    8. **Referral** -- any non-empty referrer domain not caught above.
    9. **Direct** -- fallback when no referrer is present.

    The channel classification is evaluated in SQL via a CASE expression
    for maximum performance (no per-row Python processing).

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        filters: Optional list of column filters to narrow the dataset.

    Returns:
        List of dicts, each containing:
        - ``channel`` (str): The classified marketing channel name.
        - ``visitors`` (int): Unique visitor (visit_id) count.
        - ``pageviews`` (int): Total pageview count.
        - ``bounceRate`` (float): Percentage of single-page visits.
        - ``avgDuration`` (float): Average visit duration in seconds.
        Sorted by visitors descending.
    """
    filters = filters or []
    filter_where, filter_params, session_join = prepare_filters(filters)

    # The CASE waterfall below is order-dependent: utm_medium checks take
    # priority over referrer-domain-based detection, so paid campaigns are
    # never misclassified as organic social or referral traffic.
    #
    # The final Referral check explicitly excludes self-referrers (where
    # the referring domain equals the page hostname): internal navigation
    # is not an external referral, so those visits fall through to the
    # Direct bucket -- consistent with the Top Referrers widget.
    rows = raw_query(
        f"""WITH visit_stats AS (
      SELECT
        we.visit_id,
        CASE
          WHEN we.utm_medium IN (
            'cpc', 'ppc', 'paid', 'paidsearch', 'paid-search'
          ) THEN 'Paid Search'
          WHEN we.utm_medium IN ('display', 'banner', 'cpm') THEN 'Display'
          WHEN we.utm_medium IN ('social', 'social-media', 'sm') THEN 'Paid Social'
          WHEN we.utm_medium = 'email' THEN 'Email'
          WHEN we.utm_medium = 'affiliate' THEN 'Affiliate'
          WHEN we.utm_source IN ('google', 'bing', 'yahoo', 'duckduckgo', 'baidu', 'yandex')
            AND (we.utm_medium IS NULL OR we.utm_medium = 'organic') THEN 'Organic Search'
          WHEN {_NORM_REFERRER} IN ('t.co', 'facebook.com', 'l.facebook.com', 'instagram.com',
            'linkedin.com', 'lnkd.in', 'reddit.com', 'youtube.com', 'tiktok.com', 'pinterest.com',
            'x.com', 'threads.net', 'mastodon.social') THEN 'Organic Social'
          WHEN {_NORM_REFERRER} IS NOT NULL AND {_NORM_REFERRER} != ''
            AND {_NORM_REFERRER} != COALESCE({_NORM_HOSTNAME}, '') THEN 'Referral'
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


def get_click_id_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Aggregate engagement metrics for visits attributed to ad-platform click IDs.

    Identifies paid traffic by the presence of platform-specific click-ID
    query parameters captured by the tracker:

    - ``gclid`` -- Google Ads
    - ``fbclid`` -- Meta / Facebook Ads
    - ``msclkid`` -- Microsoft Ads (Bing)
    - ``ttclid`` -- TikTok Ads
    - ``twclid`` -- Twitter / X Ads
    - ``li_fat_id`` -- LinkedIn Ads

    Each visit is mapped to the *first* non-NULL click ID via a CASE
    expression (priority order matches the list above).  Only visits
    carrying at least one click ID are included in the results.

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        filters: Optional list of column filters to narrow the dataset.

    Returns:
        List of dicts, each containing:
        - ``platform`` (str): Human-readable ad platform name with the
          click-ID field in parentheses, e.g. ``"Google Ads (gclid)"``.
        - ``visitors`` (int): Unique visitor (visit_id) count.
        - ``pageviews`` (int): Total pageview count.
        - ``bounceRate`` (float): Percentage of single-page visits.
        - ``avgDuration`` (float): Average visit duration in seconds.
        Sorted by visitors descending.
    """
    filters = filters or []
    filter_where, filter_params, session_join = prepare_filters(filters)

    # The CASE expression maps visit to platform by checking click-ID fields
    # in priority order.  The OR-chain in the WHERE clause pre-filters to
    # only rows carrying at least one click ID (avoids scanning the entire
    # event table when click-ID traffic is a small fraction).
    rows = raw_query(
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


def get_referrer_pages(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    referrer_domain: str,
    limit: int = 20,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """List the most-viewed landing pages for a specific referrer domain.

    Provides a drill-down from the referrer overview: given a referrer
    domain (or the special value ``(direct)`` for no-referrer traffic),
    returns the pages those visitors landed on, ranked by pageview count.

    When ``referrer_domain`` is ``(direct)``, the SQL condition checks
    for NULL referrer rather than matching a domain string, since direct
    traffic has no referrer header at all.

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        referrer_domain: The domain to filter by.  Use ``(direct)``
            for traffic with no referrer.
        limit: Maximum number of pages to return (default 20).
        filters: Optional list of column filters to narrow the dataset.

    Returns:
        List of dicts, each containing:
        - ``urlPath`` (str): The page URL path.
        - ``visitors`` (int): Unique session count.
        - ``pageviews`` (int): Total pageview count.
        Sorted by pageviews descending.
    """
    filters = filters or []
    filter_where, filter_params, session_join = prepare_filters(filters)

    # Special handling: "(direct)" means no referrer at all (NULL),
    # so we use IS NULL instead of an equality check.
    is_direct = referrer_domain == "(direct)"
    # Build the WHERE clause fragment: NULL for direct traffic,
    # parameterised equality for a specific referrer domain.
    _placeholder = "{{referrerDomain}}"
    referrer_condition = (
        f"AND {_NORM_REFERRER} IS NULL" if is_direct else f"AND {_NORM_REFERRER} = {_placeholder}"
    )
    extra_params: dict[str, Any] = {}
    if not is_direct:
        extra_params["referrerDomain"] = referrer_domain

    rows = raw_query(
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


def get_hostname_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 50,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Compute engagement metrics grouped by the hostname serving the page.

    Useful for multi-domain setups (e.g. ``www.example.com`` vs
    ``blog.example.com``) to understand how traffic distributes across
    hostnames.  Rows with NULL or empty hostname are excluded.

    Uses the same two-phase CTE pattern as ``get_referrer_metrics``:
    inner CTE computes per-visit page count and duration, outer query
    aggregates by hostname.

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        limit: Maximum number of hostname rows to return (default 50).
        filters: Optional list of column filters to narrow the dataset.

    Returns:
        List of dicts, each containing:
        - ``hostname`` (str): The hostname (e.g. ``"blog.example.com"``).
        - ``visitors`` (int): Unique visitor (visit_id) count.
        - ``pageviews`` (int): Total pageview count.
        - ``bounceRate`` (float): Percentage of single-page visits.
        - ``avgDuration`` (float): Average visit duration in seconds.
        Sorted by visitors descending.
    """
    filters = filters or []
    filter_where, filter_params, session_join = prepare_filters(filters)

    rows = raw_query(
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
