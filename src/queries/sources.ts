import { rawQuery, buildFilterSQL, type Filter } from "@/lib/queries";

export interface ReferrerMetrics {
  referrerDomain: string;
  visitors: number;
  pageviews: number;
  bounceRate: number;
  avgDuration: number;
}

/**
 * Get referrer metrics with bounce rate and duration.
 */
export async function getReferrerMetrics(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  limit = 50,
  filters: Filter[] = []
): Promise<ReferrerMetrics[]> {
  const { sql: filterWhere, params: filterParams, needsSessionJoin } =
    buildFilterSQL(filters);

  const sessionJoin = needsSessionJoin
    ? "JOIN session s ON s.session_id = we.session_id"
    : "";

  const results = await rawQuery<{
    referrer_domain: string;
    visitors: bigint;
    pageviews: bigint;
    bounce_rate: number;
    avg_duration: number;
  }>(
    `WITH visit_stats AS (
      SELECT
        we.visit_id,
        we.referrer_domain,
        COUNT(*) AS pages,
        EXTRACT(EPOCH FROM (MAX(we.created_at) - MIN(we.created_at))) AS duration
      FROM website_event we
      ${sessionJoin}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        ${filterWhere}
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
    LIMIT ${limit}`,
    { websiteId, startDate, endDate, ...filterParams }
  );

  return results.map((r) => ({
    referrerDomain: r.referrer_domain,
    visitors: Number(r.visitors),
    pageviews: Number(r.pageviews),
    bounceRate: r.bounce_rate ?? 0,
    avgDuration: r.avg_duration ?? 0,
  }));
}

export interface UTMMetrics {
  utmSource: string | null;
  utmMedium: string | null;
  utmCampaign: string | null;
  visitors: number;
  pageviews: number;
}

/**
 * Get UTM campaign metrics.
 */
export async function getUTMMetrics(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  groupBy: "utm_source" | "utm_medium" | "utm_campaign" = "utm_source",
  limit = 50,
  filters: Filter[] = []
): Promise<UTMMetrics[]> {
  const validFields = ["utm_source", "utm_medium", "utm_campaign"];
  if (!validFields.includes(groupBy)) return [];

  const { sql: filterWhere, params: filterParams, needsSessionJoin } =
    buildFilterSQL(filters);

  const sessionJoin = needsSessionJoin
    ? "JOIN session s ON s.session_id = we.session_id"
    : "";

  const results = await rawQuery<{
    utm_source: string | null;
    utm_medium: string | null;
    utm_campaign: string | null;
    visitors: bigint;
    pageviews: bigint;
  }>(
    `SELECT
      we.utm_source,
      we.utm_medium,
      we.utm_campaign,
      COUNT(DISTINCT we.session_id)::bigint AS visitors,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    ${sessionJoin}
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND we.${groupBy} IS NOT NULL
      ${filterWhere}
    GROUP BY we.utm_source, we.utm_medium, we.utm_campaign
    ORDER BY visitors DESC
    LIMIT ${limit}`,
    { websiteId, startDate, endDate, ...filterParams }
  );

  return results.map((r) => ({
    utmSource: r.utm_source,
    utmMedium: r.utm_medium,
    utmCampaign: r.utm_campaign,
    visitors: Number(r.visitors),
    pageviews: Number(r.pageviews),
  }));
}

export interface UTMDetailMetrics {
  value: string;
  visitors: number;
  pageviews: number;
  bounceRate: number;
  avgDuration: number;
}

/**
 * Get detailed UTM metrics for a single dimension with bounce rate and duration.
 */
export async function getUTMDetailMetrics(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  dimension: "utm_source" | "utm_medium" | "utm_campaign" | "utm_content" | "utm_term",
  limit = 50,
  filters: Filter[] = []
): Promise<UTMDetailMetrics[]> {
  const validDims = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"];
  if (!validDims.includes(dimension)) return [];

  const { sql: filterWhere, params: filterParams, needsSessionJoin } =
    buildFilterSQL(filters);

  const sessionJoin = needsSessionJoin
    ? "JOIN session s ON s.session_id = we.session_id"
    : "";

  const results = await rawQuery<{
    value: string;
    visitors: bigint;
    pageviews: bigint;
    bounce_rate: number;
    avg_duration: number;
  }>(
    `WITH visit_stats AS (
      SELECT
        we.visit_id,
        we.${dimension} AS dim_value,
        COUNT(*) AS pages,
        EXTRACT(EPOCH FROM (MAX(we.created_at) - MIN(we.created_at))) AS duration
      FROM website_event we
      ${sessionJoin}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        AND we.${dimension} IS NOT NULL
        ${filterWhere}
      GROUP BY we.visit_id, we.${dimension}
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
    LIMIT ${limit}`,
    { websiteId, startDate, endDate, ...filterParams }
  );

  return results.map((r) => ({
    value: r.value,
    visitors: Number(r.visitors),
    pageviews: Number(r.pageviews),
    bounceRate: r.bounce_rate ?? 0,
    avgDuration: r.avg_duration ?? 0,
  }));
}

export interface ChannelMetrics {
  channel: string;
  visitors: number;
  pageviews: number;
  bounceRate: number;
  avgDuration: number;
}

/**
 * Get channel grouping metrics (organic, paid, social, email, direct, referral).
 */
export async function getChannelMetrics(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  filters: Filter[] = []
): Promise<ChannelMetrics[]> {
  const { sql: filterWhere, params: filterParams, needsSessionJoin } =
    buildFilterSQL(filters);

  const sessionJoin = needsSessionJoin
    ? "JOIN session s ON s.session_id = we.session_id"
    : "";

  const results = await rawQuery<{
    channel: string;
    visitors: bigint;
    pageviews: bigint;
    bounce_rate: number;
    avg_duration: number;
  }>(
    `WITH visit_stats AS (
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
      ${sessionJoin}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        ${filterWhere}
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
    ORDER BY visitors DESC`,
    { websiteId, startDate, endDate, ...filterParams }
  );

  return results.map((r) => ({
    channel: r.channel,
    visitors: Number(r.visitors),
    pageviews: Number(r.pageviews),
    bounceRate: r.bounce_rate ?? 0,
    avgDuration: r.avg_duration ?? 0,
  }));
}

export interface ClickIdMetrics {
  platform: string;
  visitors: number;
  pageviews: number;
  bounceRate: number;
  avgDuration: number;
}

/**
 * Click ID analysis — counts visits that arrived with gclid, fbclid, msclkid, etc.
 * Each row represents a paid traffic platform identified by its click ID column.
 */
export async function getClickIdMetrics(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  filters: Filter[] = []
): Promise<ClickIdMetrics[]> {
  const { sql: filterWhere, params: filterParams, needsSessionJoin } =
    buildFilterSQL(filters);

  const sessionJoin = needsSessionJoin
    ? "JOIN session s ON s.session_id = we.session_id"
    : "";

  const results = await rawQuery<{
    platform: string;
    visitors: bigint;
    pageviews: bigint;
    bounce_rate: number;
    avg_duration: number;
  }>(
    `WITH click_ids AS (
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
      ${sessionJoin}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        AND (we.gclid IS NOT NULL OR we.fbclid IS NOT NULL OR we.msclkid IS NOT NULL
             OR we.ttclid IS NOT NULL OR we.twclid IS NOT NULL OR we.li_fat_id IS NOT NULL)
        ${filterWhere}
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
    ORDER BY visitors DESC`,
    { websiteId, startDate, endDate, ...filterParams }
  );

  return results.map((r) => ({
    platform: r.platform,
    visitors: Number(r.visitors),
    pageviews: Number(r.pageviews),
    bounceRate: r.bounce_rate ?? 0,
    avgDuration: r.avg_duration ?? 0,
  }));
}

export interface ReferrerPageMetrics {
  urlPath: string;
  visitors: number;
  pageviews: number;
}

/**
 * Get top pages visited from a specific referrer domain.
 * Used for referrer drill-down: click a source to see which pages that source drives traffic to.
 */
export async function getReferrerPages(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  referrerDomain: string,
  limit = 20,
  filters: Filter[] = []
): Promise<ReferrerPageMetrics[]> {
  const { sql: filterWhere, params: filterParams, needsSessionJoin } =
    buildFilterSQL(filters);

  const sessionJoin = needsSessionJoin
    ? "JOIN session s ON s.session_id = we.session_id"
    : "";

  // Handle "(direct)" as NULL referrer_domain
  const isDirect = referrerDomain === "(direct)";

  const results = await rawQuery<{
    url_path: string;
    visitors: bigint;
    pageviews: bigint;
  }>(
    `SELECT
      we.url_path,
      COUNT(DISTINCT we.session_id)::bigint AS visitors,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    ${sessionJoin}
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      ${isDirect ? "AND we.referrer_domain IS NULL" : "AND we.referrer_domain = {{referrerDomain}}"}
      ${filterWhere}
    GROUP BY we.url_path
    ORDER BY pageviews DESC
    LIMIT ${limit}`,
    { websiteId, startDate, endDate, ...(isDirect ? {} : { referrerDomain }), ...filterParams }
  );

  return results.map((r) => ({
    urlPath: r.url_path,
    visitors: Number(r.visitors),
    pageviews: Number(r.pageviews),
  }));
}

export interface HostnameMetrics {
  hostname: string;
  visitors: number;
  pageviews: number;
  bounceRate: number;
  avgDuration: number;
}

/**
 * Get hostname breakdown metrics — useful when a single Umami site tracks multiple subdomains.
 */
export async function getHostnameMetrics(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  limit = 50,
  filters: Filter[] = []
): Promise<HostnameMetrics[]> {
  const { sql: filterWhere, params: filterParams, needsSessionJoin } =
    buildFilterSQL(filters);

  const sessionJoin = needsSessionJoin
    ? "JOIN session s ON s.session_id = we.session_id"
    : "";

  const results = await rawQuery<{
    hostname: string;
    visitors: bigint;
    pageviews: bigint;
    bounce_rate: number;
    avg_duration: number;
  }>(
    `WITH visit_stats AS (
      SELECT
        we.visit_id,
        we.hostname,
        COUNT(*) AS pages,
        EXTRACT(EPOCH FROM (MAX(we.created_at) - MIN(we.created_at))) AS duration
      FROM website_event we
      ${sessionJoin}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        AND we.hostname IS NOT NULL AND we.hostname != ''
        ${filterWhere}
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
    LIMIT ${limit}`,
    { websiteId, startDate, endDate, ...filterParams }
  );

  return results.map((r) => ({
    hostname: r.hostname,
    visitors: Number(r.visitors),
    pageviews: Number(r.pageviews),
    bounceRate: r.bounce_rate ?? 0,
    avgDuration: r.avg_duration ?? 0,
  }));
}
