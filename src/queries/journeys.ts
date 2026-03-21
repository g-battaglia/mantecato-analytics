import { rawQuery } from "@/lib/queries";

export interface JourneyPath {
  path: string[];
  count: number;
  percentage: number;
}

/**
 * Get top user journey paths (sequences of pages within visits).
 */
export async function getJourneys(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  pathLength = 3,
  limit = 20
): Promise<JourneyPath[]> {
  // Build array_agg of the first N pages per visit, then group
  const results = await rawQuery<{
    journey: string[];
    count: bigint;
  }>(
    `WITH visit_pages AS (
      SELECT
        visit_id,
        url_path,
        ROW_NUMBER() OVER (PARTITION BY visit_id ORDER BY created_at) AS rn
      FROM website_event
      WHERE website_id = {{websiteId::uuid}}
        AND created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND event_type = 1
    ),
    visit_journeys AS (
      SELECT
        visit_id,
        array_agg(url_path ORDER BY rn) AS journey
      FROM visit_pages
      WHERE rn <= ${pathLength}
      GROUP BY visit_id
      HAVING COUNT(*) >= 2
    )
    SELECT
      journey,
      COUNT(*)::bigint AS count
    FROM visit_journeys
    GROUP BY journey
    ORDER BY count DESC
    LIMIT ${limit}`,
    { websiteId, startDate, endDate }
  );

  const total = results.reduce((sum, r) => sum + Number(r.count), 0);

  return results.map((r) => ({
    path: r.journey,
    count: Number(r.count),
    percentage: total > 0 ? (Number(r.count) / total) * 100 : 0,
  }));
}
