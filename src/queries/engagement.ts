import { rawQuery, buildFilterSQL, type Filter } from "@/lib/queries";

/**
 * Visit duration distribution — histogram buckets.
 * Shows how many visits fall into each duration bucket.
 */
export interface DurationBucket {
  bucket: string;
  bucketOrder: number;
  visits: number;
  percentage: number;
}

export async function getDurationDistribution(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  filters: Filter[] = []
): Promise<DurationBucket[]> {
  const { sql: filterWhere, params: filterParams, needsSessionJoin } =
    buildFilterSQL(filters);

  const sessionJoin = needsSessionJoin
    ? "JOIN session s ON s.session_id = we.session_id"
    : "";

  const results = await rawQuery<{
    bucket: string;
    bucket_order: number;
    visits: bigint;
  }>(
    `WITH visit_durations AS (
      SELECT
        we.visit_id,
        EXTRACT(EPOCH FROM (MAX(we.created_at) - MIN(we.created_at))) AS duration_secs
      FROM website_event we
      ${sessionJoin}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        ${filterWhere}
      GROUP BY we.visit_id
    ),
    bucketed AS (
      SELECT
        CASE
          WHEN duration_secs = 0 THEN '0s (bounce)'
          WHEN duration_secs < 10 THEN '1-10s'
          WHEN duration_secs < 30 THEN '10-30s'
          WHEN duration_secs < 60 THEN '30s-1m'
          WHEN duration_secs < 180 THEN '1-3m'
          WHEN duration_secs < 600 THEN '3-10m'
          WHEN duration_secs < 1800 THEN '10-30m'
          ELSE '30m+'
        END AS bucket,
        CASE
          WHEN duration_secs = 0 THEN 0
          WHEN duration_secs < 10 THEN 1
          WHEN duration_secs < 30 THEN 2
          WHEN duration_secs < 60 THEN 3
          WHEN duration_secs < 180 THEN 4
          WHEN duration_secs < 600 THEN 5
          WHEN duration_secs < 1800 THEN 6
          ELSE 7
        END AS bucket_order
      FROM visit_durations
    )
    SELECT bucket, bucket_order, COUNT(*)::bigint AS visits
    FROM bucketed
    GROUP BY bucket, bucket_order
    ORDER BY bucket_order`,
    { websiteId, startDate, endDate, ...filterParams }
  );

  const total = results.reduce((sum, r) => sum + Number(r.visits), 0);

  return results.map((r) => ({
    bucket: r.bucket,
    bucketOrder: r.bucket_order,
    visits: Number(r.visits),
    percentage: total > 0 ? (Number(r.visits) / total) * 100 : 0,
  }));
}

/**
 * Duration percentiles (p50, p75, p90, p95, p99).
 */
export interface DurationPercentiles {
  p50: number;
  p75: number;
  p90: number;
  p95: number;
  p99: number;
  avg: number;
  median: number;
  min: number;
  max: number;
  totalVisits: number;
}

export async function getDurationPercentiles(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  filters: Filter[] = []
): Promise<DurationPercentiles> {
  const { sql: filterWhere, params: filterParams, needsSessionJoin } =
    buildFilterSQL(filters);

  const sessionJoin = needsSessionJoin
    ? "JOIN session s ON s.session_id = we.session_id"
    : "";

  const results = await rawQuery<{
    p50: number;
    p75: number;
    p90: number;
    p95: number;
    p99: number;
    avg: number;
    min_dur: number;
    max_dur: number;
    total_visits: bigint;
  }>(
    `WITH visit_durations AS (
      SELECT
        we.visit_id,
        EXTRACT(EPOCH FROM (MAX(we.created_at) - MIN(we.created_at))) AS duration_secs
      FROM website_event we
      ${sessionJoin}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        ${filterWhere}
      GROUP BY we.visit_id
      HAVING COUNT(*) > 1
    )
    SELECT
      PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_secs) AS p50,
      PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY duration_secs) AS p75,
      PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY duration_secs) AS p90,
      PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_secs) AS p95,
      PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration_secs) AS p99,
      AVG(duration_secs) AS avg,
      MIN(duration_secs) AS min_dur,
      MAX(duration_secs) AS max_dur,
      COUNT(*)::bigint AS total_visits
    FROM visit_durations`,
    { websiteId, startDate, endDate, ...filterParams }
  );

  const row = results[0];
  return {
    p50: Number(row?.p50 ?? 0),
    p75: Number(row?.p75 ?? 0),
    p90: Number(row?.p90 ?? 0),
    p95: Number(row?.p95 ?? 0),
    p99: Number(row?.p99 ?? 0),
    avg: Number(row?.avg ?? 0),
    median: Number(row?.p50 ?? 0),
    min: Number(row?.min_dur ?? 0),
    max: Number(row?.max_dur ?? 0),
    totalVisits: Number(row?.total_visits ?? 0),
  };
}

/**
 * Duration by page — avg, median, p90 time on each page.
 */
export interface PageDuration {
  urlPath: string;
  views: number;
  avgDuration: number;
  medianDuration: number;
  p90Duration: number;
}

export async function getDurationByPage(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  limit = 20,
  filters: Filter[] = []
): Promise<PageDuration[]> {
  const { sql: filterWhere, params: filterParams, needsSessionJoin } =
    buildFilterSQL(filters);

  const sessionJoin = needsSessionJoin
    ? "JOIN session s ON s.session_id = we.session_id"
    : "";

  const results = await rawQuery<{
    url_path: string;
    views: bigint;
    avg_duration: number;
    median_duration: number;
    p90_duration: number;
  }>(
    `WITH page_sequence AS (
      SELECT
        we.url_path,
        we.visit_id,
        we.created_at,
        LEAD(we.created_at) OVER (PARTITION BY we.visit_id ORDER BY we.created_at) AS next_page_at
      FROM website_event we
      ${sessionJoin}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        ${filterWhere}
    )
    SELECT
      url_path,
      COUNT(*)::bigint AS views,
      AVG(EXTRACT(EPOCH FROM (next_page_at - created_at)))
        FILTER (WHERE next_page_at IS NOT NULL) AS avg_duration,
      PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (next_page_at - created_at))
      ) FILTER (WHERE next_page_at IS NOT NULL) AS median_duration,
      PERCENTILE_CONT(0.9) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (next_page_at - created_at))
      ) FILTER (WHERE next_page_at IS NOT NULL) AS p90_duration
    FROM page_sequence
    GROUP BY url_path
    HAVING COUNT(*) FILTER (WHERE next_page_at IS NOT NULL) > 0
    ORDER BY views DESC
    LIMIT ${limit}`,
    { websiteId, startDate, endDate, ...filterParams }
  );

  return results.map((r) => ({
    urlPath: r.url_path,
    views: Number(r.views),
    avgDuration: Number(r.avg_duration ?? 0),
    medianDuration: Number(r.median_duration ?? 0),
    p90Duration: Number(r.p90_duration ?? 0),
  }));
}

/**
 * Bounce rate breakdown by page.
 */
export interface PageBounceRate {
  urlPath: string;
  totalVisits: number;
  bounces: number;
  bounceRate: number;
}

export async function getBounceRateByPage(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  limit = 20,
  filters: Filter[] = []
): Promise<PageBounceRate[]> {
  const { sql: filterWhere, params: filterParams, needsSessionJoin } =
    buildFilterSQL(filters);

  const sessionJoin = needsSessionJoin
    ? "JOIN session s ON s.session_id = we.session_id"
    : "";

  const results = await rawQuery<{
    url_path: string;
    total_visits: bigint;
    bounces: bigint;
    bounce_rate: number;
  }>(
    `WITH entry_pages AS (
      SELECT
        we.visit_id,
        we.url_path,
        ROW_NUMBER() OVER (PARTITION BY we.visit_id ORDER BY we.created_at ASC) AS rn,
        COUNT(*) OVER (PARTITION BY we.visit_id) AS pages_in_visit
      FROM website_event we
      ${sessionJoin}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        ${filterWhere}
    )
    SELECT
      url_path,
      COUNT(*)::bigint AS total_visits,
      COUNT(*) FILTER (WHERE pages_in_visit = 1)::bigint AS bounces,
      CASE WHEN COUNT(*) > 0
        THEN (COUNT(*) FILTER (WHERE pages_in_visit = 1)::float / COUNT(*)::float) * 100
        ELSE 0
      END AS bounce_rate
    FROM entry_pages
    WHERE rn = 1
    GROUP BY url_path
    HAVING COUNT(*) >= 2
    ORDER BY total_visits DESC
    LIMIT ${limit}`,
    { websiteId, startDate, endDate, ...filterParams }
  );

  return results.map((r) => ({
    urlPath: r.url_path,
    totalVisits: Number(r.total_visits),
    bounces: Number(r.bounces),
    bounceRate: Number(r.bounce_rate),
  }));
}

/**
 * Bounce rate breakdown by source (referrer domain).
 */
export interface SourceBounceRate {
  referrerDomain: string;
  totalVisits: number;
  bounces: number;
  bounceRate: number;
}

export async function getBounceRateBySource(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  limit = 20,
  filters: Filter[] = []
): Promise<SourceBounceRate[]> {
  const { sql: filterWhere, params: filterParams, needsSessionJoin } =
    buildFilterSQL(filters);

  const sessionJoin = needsSessionJoin
    ? "JOIN session s ON s.session_id = we.session_id"
    : "";

  const results = await rawQuery<{
    referrer_domain: string;
    total_visits: bigint;
    bounces: bigint;
    bounce_rate: number;
  }>(
    `WITH visit_info AS (
      SELECT
        we.visit_id,
        we.referrer_domain,
        ROW_NUMBER() OVER (PARTITION BY we.visit_id ORDER BY we.created_at ASC) AS rn,
        COUNT(*) OVER (PARTITION BY we.visit_id) AS pages_in_visit
      FROM website_event we
      ${sessionJoin}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        ${filterWhere}
    )
    SELECT
      COALESCE(referrer_domain, '(direct)') AS referrer_domain,
      COUNT(*)::bigint AS total_visits,
      COUNT(*) FILTER (WHERE pages_in_visit = 1)::bigint AS bounces,
      CASE WHEN COUNT(*) > 0
        THEN (COUNT(*) FILTER (WHERE pages_in_visit = 1)::float / COUNT(*)::float) * 100
        ELSE 0
      END AS bounce_rate
    FROM visit_info
    WHERE rn = 1
    GROUP BY referrer_domain
    HAVING COUNT(*) >= 2
    ORDER BY total_visits DESC
    LIMIT ${limit}`,
    { websiteId, startDate, endDate, ...filterParams }
  );

  return results.map((r) => ({
    referrerDomain: r.referrer_domain,
    totalVisits: Number(r.total_visits),
    bounces: Number(r.bounces),
    bounceRate: Number(r.bounce_rate),
  }));
}
