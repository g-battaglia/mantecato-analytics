import { rawQuery, buildFilterSQL, type Filter } from "@/lib/queries";

export interface WebsiteStats {
  pageviews: number;
  visitors: number;
  visits: number;
  bounces: number;
  totaltime: number;
}

/**
 * Get website stats for a date range (adapted from Umami's getWebsiteStats).
 */
export async function getWebsiteStats(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  filters: Filter[] = []
): Promise<WebsiteStats> {
  const { sql: filterWhere, params: filterParams, needsSessionJoin } =
    buildFilterSQL(filters);

  const sessionJoin = needsSessionJoin
    ? "JOIN session s ON s.session_id = we.session_id"
    : "";

  const results = await rawQuery<{
    pageviews: bigint;
    visitors: bigint;
    visits: bigint;
    bounces: bigint;
    totaltime: bigint;
  }>(
    `SELECT
      COALESCE(SUM(t.c), 0)::bigint AS pageviews,
      COUNT(DISTINCT t.session_id)::bigint AS visitors,
      COUNT(DISTINCT t.visit_id)::bigint AS visits,
      COALESCE(SUM(CASE WHEN t.c = 1 THEN 1 ELSE 0 END), 0)::bigint AS bounces,
      COALESCE(SUM(FLOOR(EXTRACT(EPOCH FROM (t.max_time - t.min_time)))), 0)::bigint AS totaltime
    FROM (
      SELECT
        we.session_id, we.visit_id,
        COUNT(*) AS c,
        MIN(we.created_at) AS min_time,
        MAX(we.created_at) AS max_time
      FROM website_event we
      ${sessionJoin}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        ${filterWhere}
      GROUP BY we.session_id, we.visit_id
    ) AS t`,
    { websiteId, startDate, endDate, ...filterParams }
  );

  const row = results[0];
  return {
    pageviews: Number(row?.pageviews ?? 0),
    visitors: Number(row?.visitors ?? 0),
    visits: Number(row?.visits ?? 0),
    bounces: Number(row?.bounces ?? 0),
    totaltime: Number(row?.totaltime ?? 0),
  };
}

export interface PageviewTimeSeries {
  time: string;
  pageviews: number;
  visitors: number;
}

/**
 * Get pageview time series for a date range.
 */
export async function getPageviewTimeSeries(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  granularity: string,
  filters: Filter[] = []
): Promise<PageviewTimeSeries[]> {
  const validGranularities = ["minute", "hour", "day", "week", "month"];
  const gran = validGranularities.includes(granularity) ? granularity : "day";
  const { sql: filterWhere, params: filterParams, needsSessionJoin } =
    buildFilterSQL(filters);

  const sessionJoin = needsSessionJoin
    ? "JOIN session s ON s.session_id = we.session_id"
    : "";

  const results = await rawQuery<{
    time: Date;
    pageviews: bigint;
    visitors: bigint;
  }>(
    `SELECT
      date_trunc('${gran}', we.created_at) AS time,
      COUNT(*)::bigint AS pageviews,
      COUNT(DISTINCT we.session_id)::bigint AS visitors
    FROM website_event we
    ${sessionJoin}
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      ${filterWhere}
    GROUP BY 1
    ORDER BY 1 ASC`,
    { websiteId, startDate, endDate, ...filterParams }
  );

  return results.map((r) => ({
    time: r.time instanceof Date ? r.time.toISOString() : String(r.time),
    pageviews: Number(r.pageviews),
    visitors: Number(r.visitors),
  }));
}

export interface TopPage {
  urlPath: string;
  views: number;
  visitors: number;
}

/**
 * Get top pages for a date range.
 */
export async function getTopPages(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  limit = 10,
  filters: Filter[] = []
): Promise<TopPage[]> {
  const { sql: filterWhere, params: filterParams, needsSessionJoin } =
    buildFilterSQL(filters);

  const sessionJoin = needsSessionJoin
    ? "JOIN session s ON s.session_id = we.session_id"
    : "";

  const results = await rawQuery<{
    url_path: string;
    views: bigint;
    visitors: bigint;
  }>(
    `SELECT
      we.url_path,
      COUNT(*)::bigint AS views,
      COUNT(DISTINCT we.session_id)::bigint AS visitors
    FROM website_event we
    ${sessionJoin}
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      ${filterWhere}
    GROUP BY we.url_path
    ORDER BY views DESC
    LIMIT ${limit}`,
    { websiteId, startDate, endDate, ...filterParams }
  );

  return results.map((r) => ({
    urlPath: r.url_path,
    views: Number(r.views),
    visitors: Number(r.visitors),
  }));
}

export interface TopReferrer {
  referrerDomain: string;
  visitors: number;
  pageviews: number;
}

/**
 * Get top referrers for a date range.
 */
export async function getTopReferrers(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  limit = 10,
  filters: Filter[] = []
): Promise<TopReferrer[]> {
  const { sql: filterWhere, params: filterParams, needsSessionJoin } =
    buildFilterSQL(filters);

  const sessionJoin = needsSessionJoin
    ? "JOIN session s ON s.session_id = we.session_id"
    : "";

  const results = await rawQuery<{
    referrer_domain: string;
    visitors: bigint;
    pageviews: bigint;
  }>(
    `SELECT
      we.referrer_domain,
      COUNT(DISTINCT we.session_id)::bigint AS visitors,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    ${sessionJoin}
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND we.referrer_domain IS NOT NULL
      AND we.referrer_domain != ''
      ${filterWhere}
    GROUP BY we.referrer_domain
    ORDER BY visitors DESC
    LIMIT ${limit}`,
    { websiteId, startDate, endDate, ...filterParams }
  );

  return results.map((r) => ({
    referrerDomain: r.referrer_domain,
    visitors: Number(r.visitors),
    pageviews: Number(r.pageviews),
  }));
}

export interface TopEvent {
  eventName: string;
  count: number;
  visitors: number;
}

/**
 * Get top events for a date range.
 */
export async function getTopEvents(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  limit = 10,
  filters: Filter[] = []
): Promise<TopEvent[]> {
  const { sql: filterWhere, params: filterParams, needsSessionJoin } =
    buildFilterSQL(filters);

  const sessionJoin = needsSessionJoin
    ? "JOIN session s ON s.session_id = we.session_id"
    : "";

  const results = await rawQuery<{
    event_name: string;
    count: bigint;
    visitors: bigint;
  }>(
    `SELECT
      we.event_name,
      COUNT(*)::bigint AS count,
      COUNT(DISTINCT we.session_id)::bigint AS visitors
    FROM website_event we
    ${sessionJoin}
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 2
      AND we.event_name IS NOT NULL
      ${filterWhere}
    GROUP BY we.event_name
    ORDER BY count DESC
    LIMIT ${limit}`,
    { websiteId, startDate, endDate, ...filterParams }
  );

  return results.map((r) => ({
    eventName: r.event_name,
    count: Number(r.count),
    visitors: Number(r.visitors),
  }));
}

export interface DeviceBreakdown {
  value: string;
  visitors: number;
}

/**
 * Get device breakdown (browser, os, or device) for a date range.
 * Demographic fields live on the session table.
 */
export async function getDeviceBreakdown(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  field: "browser" | "os" | "device",
  limit = 10,
  filters: Filter[] = []
): Promise<DeviceBreakdown[]> {
  const validFields = ["browser", "os", "device"];
  if (!validFields.includes(field)) return [];

  const { sql: filterWhere, params: filterParams } = buildFilterSQL(filters);

  // Always needs session join for the field itself
  const results = await rawQuery<{
    value: string;
    visitors: bigint;
  }>(
    `SELECT
      s.${field} AS value,
      COUNT(DISTINCT we.session_id)::bigint AS visitors
    FROM website_event we
    JOIN session s ON s.session_id = we.session_id
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND s.${field} IS NOT NULL
      ${filterWhere}
    GROUP BY s.${field}
    ORDER BY visitors DESC
    LIMIT ${limit}`,
    { websiteId, startDate, endDate, ...filterParams }
  );

  return results.map((r) => ({
    value: r.value,
    visitors: Number(r.visitors),
  }));
}

export interface CountryBreakdown {
  country: string;
  visitors: number;
  pageviews: number;
}

/**
 * Get country breakdown for a date range.
 * Country lives on the session table.
 */
export async function getCountryBreakdown(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  limit = 10,
  filters: Filter[] = []
): Promise<CountryBreakdown[]> {
  const { sql: filterWhere, params: filterParams } = buildFilterSQL(filters);

  const results = await rawQuery<{
    country: string;
    visitors: bigint;
    pageviews: bigint;
  }>(
    `SELECT
      s.country,
      COUNT(DISTINCT we.session_id)::bigint AS visitors,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    JOIN session s ON s.session_id = we.session_id
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND s.country IS NOT NULL
      ${filterWhere}
    GROUP BY s.country
    ORDER BY visitors DESC
    LIMIT ${limit}`,
    { websiteId, startDate, endDate, ...filterParams }
  );

  return results.map((r) => ({
    country: r.country,
    visitors: Number(r.visitors),
    pageviews: Number(r.pageviews),
  }));
}
