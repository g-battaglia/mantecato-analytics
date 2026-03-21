import { rawQuery, buildFilterSQL, type Filter } from "@/lib/queries";

export interface PageMetrics {
  urlPath: string;
  pageTitle: string | null;
  views: number;
  visitors: number;
  avgTimeOnPage: number | null;
  medianTimeOnPage: number | null;
  entries: number;
  exits: number;
  bounceRate: number;
}

/**
 * Get detailed page metrics including time on page and entry/exit data.
 * When pageMode is "slug", strips query strings and normalizes trailing slashes.
 */
export async function getPageMetrics(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  limit = 50,
  offset = 0,
  filters: Filter[] = [],
  pageMode: "path" | "slug" = "path"
): Promise<PageMetrics[]> {
  const { sql: filterWhere, params: filterParams, needsSessionJoin } =
    buildFilterSQL(filters);

  // In the CTE we use "we" alias for consistency with filter SQL
  const sessionJoinCTE = needsSessionJoin
    ? "JOIN session s ON s.session_id = we.session_id"
    : "";

  // In slug mode, normalize: strip trailing slashes, collapse to lowercase path only
  const urlExpr =
    pageMode === "slug"
      ? "REGEXP_REPLACE(SPLIT_PART(we.url_path, '?', 1), '/+$', '')"
      : "we.url_path";
  // Ensure empty slug (root with trailing slash stripped) becomes '/'
  const slugCoalesce =
    pageMode === "slug"
      ? `CASE WHEN ${urlExpr} = '' THEN '/' ELSE ${urlExpr} END`
      : urlExpr;

  const results = await rawQuery<{
    url_path: string;
    page_title: string | null;
    views: bigint;
    visitors: bigint;
    avg_time_on_page: number | null;
    median_time_on_page: number | null;
    entries: bigint;
    exits: bigint;
    bounce_rate: number;
  }>(
    `WITH filtered_events AS (
      SELECT ${slugCoalesce} AS url_path, we.page_title, we.visit_id, we.session_id, we.created_at
      FROM website_event we
      ${sessionJoinCTE}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        ${filterWhere}
    ),
    page_sequence AS (
      SELECT
        url_path,
        page_title,
        visit_id,
        session_id,
        created_at,
        LEAD(created_at) OVER (PARTITION BY visit_id ORDER BY created_at) AS next_page_at,
        ROW_NUMBER() OVER (PARTITION BY visit_id ORDER BY created_at ASC) AS rn_entry,
        ROW_NUMBER() OVER (PARTITION BY visit_id ORDER BY created_at DESC) AS rn_exit
      FROM filtered_events
    ),
    visit_bounces AS (
      SELECT visit_id, COUNT(*) AS page_count
      FROM filtered_events
      GROUP BY visit_id
    )
    SELECT
      ps.url_path,
      MAX(ps.page_title) AS page_title,
      COUNT(*)::bigint AS views,
      COUNT(DISTINCT ps.session_id)::bigint AS visitors,
      AVG(EXTRACT(EPOCH FROM (ps.next_page_at - ps.created_at)))
        FILTER (WHERE ps.next_page_at IS NOT NULL) AS avg_time_on_page,
      PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (ps.next_page_at - ps.created_at))
      ) FILTER (WHERE ps.next_page_at IS NOT NULL) AS median_time_on_page,
      COUNT(*) FILTER (WHERE ps.rn_entry = 1)::bigint AS entries,
      COUNT(*) FILTER (WHERE ps.rn_exit = 1)::bigint AS exits,
      CASE
        WHEN COUNT(*) FILTER (WHERE ps.rn_entry = 1) = 0 THEN 0
        ELSE (
          COUNT(*) FILTER (WHERE ps.rn_entry = 1 AND vb.page_count = 1)::float /
          NULLIF(COUNT(*) FILTER (WHERE ps.rn_entry = 1), 0) * 100
        )
      END AS bounce_rate
    FROM page_sequence ps
    LEFT JOIN visit_bounces vb ON ps.visit_id = vb.visit_id
    GROUP BY ps.url_path
    ORDER BY views DESC
    LIMIT ${limit} OFFSET ${offset}`,
    { websiteId, startDate, endDate, ...filterParams }
  );

  return results.map((r) => ({
    urlPath: r.url_path,
    pageTitle: r.page_title,
    views: Number(r.views),
    visitors: Number(r.visitors),
    avgTimeOnPage: r.avg_time_on_page,
    medianTimeOnPage: r.median_time_on_page,
    entries: Number(r.entries),
    exits: Number(r.exits),
    bounceRate: r.bounce_rate ?? 0,
  }));
}

export interface PageTimeSeries {
  time: string;
  views: number;
  visitors: number;
}

/**
 * Get time series for a specific page.
 */
export async function getPageTimeSeries(
  websiteId: string,
  urlPath: string,
  startDate: Date,
  endDate: Date,
  granularity: string,
  filters: Filter[] = []
): Promise<PageTimeSeries[]> {
  const validGranularities = ["minute", "hour", "day", "week", "month"];
  const gran = validGranularities.includes(granularity) ? granularity : "day";
  const { sql: filterWhere, params: filterParams, needsSessionJoin } =
    buildFilterSQL(filters);

  const sessionJoin = needsSessionJoin
    ? "JOIN session s ON s.session_id = we.session_id"
    : "";

  const results = await rawQuery<{
    time: Date;
    views: bigint;
    visitors: bigint;
  }>(
    `SELECT
      date_trunc('${gran}', we.created_at) AS time,
      COUNT(*)::bigint AS views,
      COUNT(DISTINCT we.session_id)::bigint AS visitors
    FROM website_event we
    ${sessionJoin}
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND we.url_path = {{urlPath}}
      ${filterWhere}
    GROUP BY 1
    ORDER BY 1 ASC`,
    { websiteId, startDate, endDate, urlPath, ...filterParams }
  );

  return results.map((r) => ({
    time: r.time instanceof Date ? r.time.toISOString() : String(r.time),
    views: Number(r.views),
    visitors: Number(r.visitors),
  }));
}
