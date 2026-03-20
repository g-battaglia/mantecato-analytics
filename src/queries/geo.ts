import { rawQuery } from "@/lib/queries";

export interface GeoMetrics {
  country: string;
  region: string | null;
  city: string | null;
  visitors: number;
  pageviews: number;
  visits: number;
}

/**
 * Get geographic breakdown.
 * Demographic fields (country/region/city) live on the session table.
 */
export async function getGeoMetrics(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  level: "country" | "region" | "city" = "country",
  countryFilter?: string,
  regionFilter?: string,
  limit = 50
): Promise<GeoMetrics[]> {
  let groupBy: string;
  let extraFilter = "";
  const params: Record<string, unknown> = { websiteId, startDate, endDate };

  switch (level) {
    case "city":
      groupBy = "s.country, s.region, s.city";
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
      if (countryFilter) {
        extraFilter += " AND s.country = {{countryFilter}}";
        params.countryFilter = countryFilter;
      }
      break;
    default:
      groupBy = "s.country";
  }

  const results = await rawQuery<{
    country: string;
    region: string | null;
    city: string | null;
    visitors: bigint;
    pageviews: bigint;
    visits: bigint;
  }>(
    `SELECT
      s.country,
      ${level !== "country" ? "s.region," : "NULL AS region,"}
      ${level === "city" ? "s.city," : "NULL AS city,"}
      COUNT(DISTINCT we.session_id)::bigint AS visitors,
      COUNT(*)::bigint AS pageviews,
      COUNT(DISTINCT we.visit_id)::bigint AS visits
    FROM website_event we
    JOIN session s ON s.session_id = we.session_id
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND s.country IS NOT NULL
      ${extraFilter}
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
  }));
}
