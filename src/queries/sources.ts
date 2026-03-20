import { rawQuery } from "@/lib/queries";

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
  limit = 50
): Promise<ReferrerMetrics[]> {
  const results = await rawQuery<{
    referrer_domain: string;
    visitors: bigint;
    pageviews: bigint;
    bounce_rate: number;
    avg_duration: number;
  }>(
    `WITH visit_stats AS (
      SELECT
        visit_id,
        referrer_domain,
        COUNT(*) AS pages,
        EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at))) AS duration
      FROM website_event
      WHERE website_id = {{websiteId::uuid}}
        AND created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND event_type = 1
      GROUP BY visit_id, referrer_domain
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
    { websiteId, startDate, endDate }
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
  limit = 50
): Promise<UTMMetrics[]> {
  const validFields = ["utm_source", "utm_medium", "utm_campaign"];
  if (!validFields.includes(groupBy)) return [];

  const results = await rawQuery<{
    utm_source: string | null;
    utm_medium: string | null;
    utm_campaign: string | null;
    visitors: bigint;
    pageviews: bigint;
  }>(
    `SELECT
      utm_source,
      utm_medium,
      utm_campaign,
      COUNT(DISTINCT session_id)::bigint AS visitors,
      COUNT(*)::bigint AS pageviews
    FROM website_event
    WHERE website_id = {{websiteId::uuid}}
      AND created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND event_type = 1
      AND ${groupBy} IS NOT NULL
    GROUP BY utm_source, utm_medium, utm_campaign
    ORDER BY visitors DESC
    LIMIT ${limit}`,
    { websiteId, startDate, endDate }
  );

  return results.map((r) => ({
    utmSource: r.utm_source,
    utmMedium: r.utm_medium,
    utmCampaign: r.utm_campaign,
    visitors: Number(r.visitors),
    pageviews: Number(r.pageviews),
  }));
}
