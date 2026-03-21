import { rawQuery, buildFilterSQL, type Filter } from "@/lib/queries";

export interface GeoMetrics {
  country: string;
  region: string | null;
  city: string | null;
  visitors: number;
  pageviews: number;
  visits: number;
  bounceRate: number;
  avgDuration: number;
}

/**
 * Get geographic breakdown with bounce rate and avg duration.
 * Demographic fields (country/region/city) live on the session table.
 */
export async function getGeoMetrics(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  level: "country" | "region" | "city" = "country",
  countryFilter?: string,
  regionFilter?: string,
  limit = 50,
  filters: Filter[] = []
): Promise<GeoMetrics[]> {
  let groupBy: string;
  let selectGeo: string;
  let extraFilter = "";
  const params: Record<string, unknown> = { websiteId, startDate, endDate };

  // Merge filter params
  const { sql: filterWhere, params: filterParams } = buildFilterSQL(filters);
  Object.assign(params, filterParams);

  switch (level) {
    case "city":
      groupBy = "s.country, s.region, s.city";
      selectGeo = "s.country, s.region, s.city,";
      if (countryFilter) {
        extraFilter += " AND s.country = {{countryFilter}}";
        params.countryFilter = countryFilter;
      }
      if (regionFilter) {
        extraFilter += " AND s.region = {{regionFilter}}";
        params.regionFilter = regionFilter;
      }
      break;
    case "region":
      groupBy = "s.country, s.region";
      selectGeo = "s.country, s.region, NULL AS city,";
      if (countryFilter) {
        extraFilter += " AND s.country = {{countryFilter}}";
        params.countryFilter = countryFilter;
      }
      break;
    default:
      groupBy = "s.country";
      selectGeo = "s.country, NULL AS region, NULL AS city,";
  }

  const results = await rawQuery<{
    country: string;
    region: string | null;
    city: string | null;
    visitors: bigint;
    pageviews: bigint;
    visits: bigint;
    bounce_rate: number;
    avg_duration: number;
  }>(
    `WITH visit_stats AS (
      SELECT
        ${groupBy},
        we.visit_id,
        COUNT(*) AS pages,
        EXTRACT(EPOCH FROM (MAX(we.created_at) - MIN(we.created_at))) AS duration
      FROM website_event we
      JOIN session s ON s.session_id = we.session_id
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        AND s.country IS NOT NULL
        ${extraFilter}
        ${filterWhere}
      GROUP BY ${groupBy}, we.visit_id
    )
    SELECT
      ${selectGeo}
      COUNT(DISTINCT visit_id)::bigint AS visitors,
      SUM(pages)::bigint AS pageviews,
      COUNT(visit_id)::bigint AS visits,
      CASE WHEN COUNT(*) = 0 THEN 0
        ELSE (SUM(CASE WHEN pages = 1 THEN 1 ELSE 0 END)::float / COUNT(*) * 100)
      END AS bounce_rate,
      COALESCE(AVG(duration), 0) AS avg_duration
    FROM visit_stats
    GROUP BY ${groupBy}
    ORDER BY visitors DESC
    LIMIT ${limit}`,
    params
  );

  return results.map((r) => ({
    country: r.country,
    region: r.region,
    city: r.city,
    visitors: Number(r.visitors),
    pageviews: Number(r.pageviews),
    visits: Number(r.visits),
    bounceRate: r.bounce_rate ?? 0,
    avgDuration: r.avg_duration ?? 0,
  }));
}
