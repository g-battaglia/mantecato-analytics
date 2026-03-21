import { rawQuery } from "@/lib/queries";

export interface FunnelStep {
  step: number;
  label: string;
  visitors: number;
  dropoff: number;
  conversionRate: number;
}

/**
 * Run a funnel analysis with a sequence of URL paths or event names.
 * Each step narrows the set of sessions that completed it within the window.
 */
export async function getFunnel(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  steps: Array<{ type: "url" | "event"; value: string }>,
  windowMinutes = 60
): Promise<FunnelStep[]> {
  if (steps.length < 2) return [];

  // Build dynamic CTEs for each step
  const ctes: string[] = [];
  const params: Record<string, unknown> = { websiteId, startDate, endDate };

  // Step 0: all sessions that hit the first condition
  const s0 = steps[0];
  const s0Condition =
    s0.type === "url"
      ? "we.url_path = {{step0Val}} AND we.event_type = 1"
      : "we.event_name = {{step0Val}} AND we.event_type = 2";
  params.step0Val = s0.value;

  ctes.push(`step0 AS (
    SELECT DISTINCT we.session_id, MIN(we.created_at) AS step_time
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND ${s0Condition}
    GROUP BY we.session_id
  )`);

  for (let i = 1; i < steps.length; i++) {
    const s = steps[i];
    const condition =
      s.type === "url"
        ? `we.url_path = {{step${i}Val}} AND we.event_type = 1`
        : `we.event_name = {{step${i}Val}} AND we.event_type = 2`;
    params[`step${i}Val`] = s.value;

    ctes.push(`step${i} AS (
      SELECT DISTINCT we.session_id, MIN(we.created_at) AS step_time
      FROM website_event we
      JOIN step${i - 1} prev ON we.session_id = prev.session_id
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND ${condition}
        AND we.created_at >= prev.step_time
        AND we.created_at <= prev.step_time + INTERVAL '${windowMinutes} minutes'
      GROUP BY we.session_id
    )`);
  }

  // Final query: count visitors at each step
  const selects = steps.map(
    (_, i) => `(SELECT COUNT(*) FROM step${i}) AS step${i}_count`
  );

  const sql = `WITH ${ctes.join(",\n")}
    SELECT ${selects.join(", ")}`;

  const results = await rawQuery<Record<string, bigint>>(sql, params);
  const row = results[0];

  const funnelSteps: FunnelStep[] = [];
  let prevVisitors = 0;

  for (let i = 0; i < steps.length; i++) {
    const visitors = Number(row[`step${i}_count`] ?? 0);
    const dropoff = i === 0 ? 0 : prevVisitors - visitors;
    const conversionRate =
      i === 0
        ? 100
        : prevVisitors > 0
          ? (visitors / prevVisitors) * 100
          : 0;

    funnelSteps.push({
      step: i + 1,
      label: steps[i].value,
      visitors,
      dropoff,
      conversionRate,
    });

    prevVisitors = visitors;
  }

  return funnelSteps;
}
