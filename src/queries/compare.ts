import { rawQuery } from "@/lib/queries";

export interface ComparisonStats {
  period: "current" | "previous";
  pageviews: number;
  visitors: number;
  visits: number;
  bounces: number;
  totaltime: number;
}

/**
 * Get stats for two periods for comparison.
 */
export async function getComparisonStats(
  websiteId: string,
  currentStart: Date,
  currentEnd: Date,
  previousStart: Date,
  previousEnd: Date
): Promise<ComparisonStats[]> {
  const results = await rawQuery<{
    period: string;
    pageviews: bigint;
    visitors: bigint;
    visits: bigint;
    bounces: bigint;
    totaltime: bigint;
  }>(
    `SELECT
      'current' AS period,
      COALESCE(SUM(t.c), 0)::bigint AS pageviews,
      COUNT(DISTINCT t.session_id)::bigint AS visitors,
      COUNT(DISTINCT t.visit_id)::bigint AS visits,
      COALESCE(SUM(CASE WHEN t.c = 1 THEN 1 ELSE 0 END), 0)::bigint AS bounces,
      COALESCE(SUM(FLOOR(EXTRACT(EPOCH FROM (t.max_time - t.min_time)))), 0)::bigint AS totaltime
    FROM (
      SELECT session_id, visit_id, COUNT(*) AS c,
             MIN(created_at) AS min_time, MAX(created_at) AS max_time
      FROM website_event
      WHERE website_id = {{websiteId::uuid}}
        AND created_at BETWEEN {{currentStart::timestamptz}} AND {{currentEnd::timestamptz}}
        AND event_type = 1
      GROUP BY 1, 2
    ) AS t
    UNION ALL
    SELECT
      'previous' AS period,
      COALESCE(SUM(t.c), 0)::bigint AS pageviews,
      COUNT(DISTINCT t.session_id)::bigint AS visitors,
      COUNT(DISTINCT t.visit_id)::bigint AS visits,
      COALESCE(SUM(CASE WHEN t.c = 1 THEN 1 ELSE 0 END), 0)::bigint AS bounces,
      COALESCE(SUM(FLOOR(EXTRACT(EPOCH FROM (t.max_time - t.min_time)))), 0)::bigint AS totaltime
    FROM (
      SELECT session_id, visit_id, COUNT(*) AS c,
             MIN(created_at) AS min_time, MAX(created_at) AS max_time
      FROM website_event
      WHERE website_id = {{websiteId::uuid}}
        AND created_at BETWEEN {{previousStart::timestamptz}} AND {{previousEnd::timestamptz}}
        AND event_type = 1
      GROUP BY 1, 2
    ) AS t`,
    { websiteId, currentStart, currentEnd, previousStart, previousEnd }
  );

  return results.map((r) => ({
    period: r.period as "current" | "previous",
    pageviews: Number(r.pageviews),
    visitors: Number(r.visitors),
    visits: Number(r.visits),
    bounces: Number(r.bounces),
    totaltime: Number(r.totaltime),
  }));
}
