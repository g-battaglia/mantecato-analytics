import { rawQuery } from "@/lib/queries";

export interface DeviceMetrics {
  value: string;
  visitors: number;
  pageviews: number;
  percentage: number;
}

/**
 * Get device breakdown by a specific dimension.
 * Demographic fields (browser/os/device/screen/language) live on the session table.
 */
export async function getDeviceMetrics(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  dimension: "browser" | "os" | "device" | "screen" | "language",
  limit = 20
): Promise<DeviceMetrics[]> {
  const validDimensions = ["browser", "os", "device", "screen", "language"];
  if (!validDimensions.includes(dimension)) return [];

  const results = await rawQuery<{
    value: string;
    visitors: bigint;
    pageviews: bigint;
  }>(
    `SELECT
      s.${dimension} AS value,
      COUNT(DISTINCT we.session_id)::bigint AS visitors,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    JOIN session s ON s.session_id = we.session_id
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND s.${dimension} IS NOT NULL
      AND s.${dimension} != ''
    GROUP BY s.${dimension}
    ORDER BY visitors DESC
    LIMIT ${limit}`,
    { websiteId, startDate, endDate }
  );

  const total = results.reduce((sum, r) => sum + Number(r.visitors), 0);

  return results.map((r) => ({
    value: r.value,
    visitors: Number(r.visitors),
    pageviews: Number(r.pageviews),
    percentage: total > 0 ? (Number(r.visitors) / total) * 100 : 0,
  }));
}
