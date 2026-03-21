import { rawQuery } from "@/lib/queries";

export interface RetentionCohort {
  cohort: string;
  cohortSize: number;
  periods: number[];
}

/**
 * Get cohort retention data.
 * Groups visitors by the week/month they first visited, then measures
 * how many returned in subsequent periods.
 */
export async function getRetention(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  granularity: "week" | "month" = "week"
): Promise<RetentionCohort[]> {
  const results = await rawQuery<{
    cohort: Date;
    cohort_size: bigint;
    period: number;
    retained: bigint;
  }>(
    `WITH first_visit AS (
      SELECT
        session_id,
        date_trunc('${granularity}', MIN(created_at)) AS cohort
      FROM website_event
      WHERE website_id = {{websiteId::uuid}}
        AND created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND event_type = 1
      GROUP BY session_id
    ),
    cohort_sizes AS (
      SELECT cohort, COUNT(DISTINCT session_id) AS cohort_size
      FROM first_visit
      GROUP BY cohort
    ),
    return_visits AS (
      SELECT
        fv.cohort,
        fv.session_id,
        EXTRACT(EPOCH FROM (date_trunc('${granularity}', we.created_at) - fv.cohort))
          / EXTRACT(EPOCH FROM INTERVAL '1 ${granularity}') AS period
      FROM website_event we
      JOIN first_visit fv ON we.session_id = fv.session_id
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
    )
    SELECT
      cs.cohort,
      cs.cohort_size,
      rv.period::int AS period,
      COUNT(DISTINCT rv.session_id)::bigint AS retained
    FROM cohort_sizes cs
    CROSS JOIN generate_series(0, 12) AS rv_period(p)
    LEFT JOIN return_visits rv ON rv.cohort = cs.cohort AND rv.period = rv_period.p
    WHERE rv_period.p >= 0
    GROUP BY cs.cohort, cs.cohort_size, rv.period
    ORDER BY cs.cohort, rv.period`,
    { websiteId, startDate, endDate }
  );

  // Group by cohort
  const cohortMap = new Map<
    string,
    { cohortSize: number; periods: Map<number, number> }
  >();

  for (const row of results) {
    const cohortKey =
      row.cohort instanceof Date
        ? row.cohort.toISOString()
        : String(row.cohort);
    if (!cohortMap.has(cohortKey)) {
      cohortMap.set(cohortKey, {
        cohortSize: Number(row.cohort_size),
        periods: new Map(),
      });
    }
    if (row.period != null) {
      cohortMap
        .get(cohortKey)!
        .periods.set(row.period, Number(row.retained));
    }
  }

  // Convert to array with period retention percentages
  const maxPeriods = 12;
  return Array.from(cohortMap.entries()).map(([cohort, data]) => {
    const periods: number[] = [];
    for (let i = 0; i <= maxPeriods; i++) {
      const retained = data.periods.get(i) ?? 0;
      periods.push(
        data.cohortSize > 0 ? (retained / data.cohortSize) * 100 : 0
      );
    }
    return { cohort, cohortSize: data.cohortSize, periods };
  });
}
