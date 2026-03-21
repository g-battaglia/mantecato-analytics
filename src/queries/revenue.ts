import { rawQuery } from "@/lib/queries";

export interface RevenueSummary {
  totalRevenue: number;
  transactions: number;
  uniqueCustomers: number;
  arpu: number;
}

export interface RevenueTimeSeries {
  time: string;
  revenue: number;
  transactions: number;
}

export interface RevenueByEvent {
  eventName: string;
  revenue: number;
  transactions: number;
  avgRevenue: number;
}

export interface RevenueByCountry {
  country: string;
  revenue: number;
  transactions: number;
}

/**
 * Get revenue summary for a date range.
 */
export async function getRevenueSummary(
  websiteId: string,
  startDate: Date,
  endDate: Date
): Promise<RevenueSummary> {
  const results = await rawQuery<{
    total_revenue: number;
    transactions: bigint;
    unique_customers: bigint;
  }>(
    `SELECT
      COALESCE(SUM(r.revenue), 0) AS total_revenue,
      COUNT(*)::bigint AS transactions,
      COUNT(DISTINCT r.session_id)::bigint AS unique_customers
    FROM revenue r
    WHERE r.website_id = {{websiteId::uuid}}
      AND r.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}`,
    { websiteId, startDate, endDate }
  );

  const row = results[0];
  const totalRevenue = Number(row?.total_revenue ?? 0);
  const uniqueCustomers = Number(row?.unique_customers ?? 0);

  return {
    totalRevenue,
    transactions: Number(row?.transactions ?? 0),
    uniqueCustomers,
    arpu: uniqueCustomers > 0 ? totalRevenue / uniqueCustomers : 0,
  };
}

/**
 * Get revenue time series.
 */
export async function getRevenueTimeSeries(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  granularity: string
): Promise<RevenueTimeSeries[]> {
  const validGranularities = ["hour", "day", "week", "month"];
  const gran = validGranularities.includes(granularity) ? granularity : "day";

  const results = await rawQuery<{
    time: Date;
    revenue: number;
    transactions: bigint;
  }>(
    `SELECT
      date_trunc('${gran}', r.created_at) AS time,
      COALESCE(SUM(r.revenue), 0) AS revenue,
      COUNT(*)::bigint AS transactions
    FROM revenue r
    WHERE r.website_id = {{websiteId::uuid}}
      AND r.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
    GROUP BY 1
    ORDER BY 1 ASC`,
    { websiteId, startDate, endDate }
  );

  return results.map((r) => ({
    time: r.time instanceof Date ? r.time.toISOString() : String(r.time),
    revenue: Number(r.revenue),
    transactions: Number(r.transactions),
  }));
}

/**
 * Get revenue breakdown by event name.
 */
export async function getRevenueByEvent(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  limit = 20
): Promise<RevenueByEvent[]> {
  const results = await rawQuery<{
    event_name: string;
    revenue: number;
    transactions: bigint;
    avg_revenue: number;
  }>(
    `SELECT
      r.event_name,
      COALESCE(SUM(r.revenue), 0) AS revenue,
      COUNT(*)::bigint AS transactions,
      COALESCE(AVG(r.revenue), 0) AS avg_revenue
    FROM revenue r
    WHERE r.website_id = {{websiteId::uuid}}
      AND r.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
    GROUP BY r.event_name
    ORDER BY revenue DESC
    LIMIT ${limit}`,
    { websiteId, startDate, endDate }
  );

  return results.map((r) => ({
    eventName: r.event_name,
    revenue: Number(r.revenue),
    transactions: Number(r.transactions),
    avgRevenue: Number(r.avg_revenue),
  }));
}

/**
 * Get revenue breakdown by country.
 */
export async function getRevenueByCountry(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  limit = 20
): Promise<RevenueByCountry[]> {
  const results = await rawQuery<{
    country: string;
    revenue: number;
    transactions: bigint;
  }>(
    `SELECT
      s.country,
      COALESCE(SUM(r.revenue), 0) AS revenue,
      COUNT(*)::bigint AS transactions
    FROM revenue r
    JOIN session s ON s.session_id = r.session_id
    WHERE r.website_id = {{websiteId::uuid}}
      AND r.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND s.country IS NOT NULL
    GROUP BY s.country
    ORDER BY revenue DESC
    LIMIT ${limit}`,
    { websiteId, startDate, endDate }
  );

  return results.map((r) => ({
    country: r.country,
    revenue: Number(r.revenue),
    transactions: Number(r.transactions),
  }));
}
