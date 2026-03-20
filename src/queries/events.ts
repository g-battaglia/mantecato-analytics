import { rawQuery } from "@/lib/queries";

export interface EventMetrics {
  eventName: string;
  count: number;
  visitors: number;
  lastTriggered: string | null;
}

/**
 * Get event list with metrics.
 */
export async function getEventMetrics(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  limit = 50
): Promise<EventMetrics[]> {
  const results = await rawQuery<{
    event_name: string;
    count: bigint;
    visitors: bigint;
    last_triggered: Date | null;
  }>(
    `SELECT
      event_name,
      COUNT(*)::bigint AS count,
      COUNT(DISTINCT session_id)::bigint AS visitors,
      MAX(created_at) AS last_triggered
    FROM website_event
    WHERE website_id = {{websiteId::uuid}}
      AND created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND event_type = 2
      AND event_name IS NOT NULL
    GROUP BY event_name
    ORDER BY count DESC
    LIMIT ${limit}`,
    { websiteId, startDate, endDate }
  );

  return results.map((r) => ({
    eventName: r.event_name,
    count: Number(r.count),
    visitors: Number(r.visitors),
    lastTriggered: r.last_triggered
      ? r.last_triggered instanceof Date
        ? r.last_triggered.toISOString()
        : String(r.last_triggered)
      : null,
  }));
}

export interface EventTimeSeries {
  time: string;
  count: number;
}

/**
 * Get time series for a specific event.
 */
export async function getEventTimeSeries(
  websiteId: string,
  eventName: string,
  startDate: Date,
  endDate: Date,
  granularity: string
): Promise<EventTimeSeries[]> {
  const validGranularities = ["minute", "hour", "day", "week", "month"];
  const gran = validGranularities.includes(granularity) ? granularity : "day";

  const results = await rawQuery<{
    time: Date;
    count: bigint;
  }>(
    `SELECT
      date_trunc('${gran}', created_at) AS time,
      COUNT(*)::bigint AS count
    FROM website_event
    WHERE website_id = {{websiteId::uuid}}
      AND created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND event_type = 2
      AND event_name = {{eventName}}
    GROUP BY 1
    ORDER BY 1 ASC`,
    { websiteId, startDate, endDate, eventName }
  );

  return results.map((r) => ({
    time: r.time instanceof Date ? r.time.toISOString() : String(r.time),
    count: Number(r.count),
  }));
}

export interface EventProperty {
  dataKey: string;
  value: string;
  count: number;
  visitors: number;
}

/**
 * Get event properties breakdown.
 */
export async function getEventProperties(
  websiteId: string,
  eventName: string,
  startDate: Date,
  endDate: Date,
  limit = 50
): Promise<EventProperty[]> {
  const results = await rawQuery<{
    data_key: string;
    value: string;
    count: bigint;
    visitors: bigint;
  }>(
    `SELECT
      ed.data_key,
      COALESCE(ed.string_value, ed.number_value::text) AS value,
      COUNT(*)::bigint AS count,
      COUNT(DISTINCT we.session_id)::bigint AS visitors
    FROM event_data ed
    JOIN website_event we ON ed.website_event_id = we.event_id
    WHERE ed.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_name = {{eventName}}
    GROUP BY 1, 2
    ORDER BY count DESC
    LIMIT ${limit}`,
    { websiteId, startDate, endDate, eventName }
  );

  return results.map((r) => ({
    dataKey: r.data_key,
    value: r.value,
    count: Number(r.count),
    visitors: Number(r.visitors),
  }));
}
