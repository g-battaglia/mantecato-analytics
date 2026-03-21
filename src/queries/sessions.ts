import { rawQuery, buildFilterSQL, type Filter } from "@/lib/queries";

export interface SessionListItem {
  sessionId: string;
  country: string | null;
  city: string | null;
  browser: string | null;
  os: string | null;
  device: string | null;
  pagesViewed: number;
  duration: number;
  startedAt: string;
}

/**
 * Get session list with metrics.
 * Demographic fields (browser/os/device/country/city) live on the session table.
 *
 * Supports additional subquery filters:
 * - visitedPage: only sessions that viewed a specific url_path
 * - triggeredEvent: only sessions that triggered a specific event_name
 */
export async function getSessionList(
  websiteId: string,
  startDate: Date,
  endDate: Date,
  limit = 50,
  offset = 0,
  filters: Filter[] = [],
  visitedPage?: string,
  triggeredEvent?: string
): Promise<SessionListItem[]> {
  // Session join is always present here
  const { sql: filterWhere, params: filterParams } = buildFilterSQL(filters);

  const extraSubqueries: string[] = [];
  const params: Record<string, unknown> = {
    websiteId,
    startDate,
    endDate,
    ...filterParams,
  };

  if (visitedPage) {
    extraSubqueries.push(
      `AND we.session_id IN (
        SELECT vp.session_id FROM website_event vp
        WHERE vp.website_id = {{websiteId::uuid}}
          AND vp.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
          AND vp.event_type = 1
          AND vp.url_path = {{visitedPage}}
      )`
    );
    params.visitedPage = visitedPage;
  }

  if (triggeredEvent) {
    extraSubqueries.push(
      `AND we.session_id IN (
        SELECT te.session_id FROM website_event te
        WHERE te.website_id = {{websiteId::uuid}}
          AND te.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
          AND te.event_type = 2
          AND te.event_name = {{triggeredEvent}}
      )`
    );
    params.triggeredEvent = triggeredEvent;
  }

  const results = await rawQuery<{
    session_id: string;
    country: string | null;
    city: string | null;
    browser: string | null;
    os: string | null;
    device: string | null;
    pages_viewed: bigint;
    duration: number;
    started_at: Date;
  }>(
    `SELECT
      we.session_id,
      s.country,
      s.city,
      s.browser,
      s.os,
      s.device,
      COUNT(*)::bigint AS pages_viewed,
      EXTRACT(EPOCH FROM (MAX(we.created_at) - MIN(we.created_at))) AS duration,
      MIN(we.created_at) AS started_at
    FROM website_event we
    JOIN session s ON s.session_id = we.session_id
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      ${filterWhere}
      ${extraSubqueries.join("\n      ")}
    GROUP BY we.session_id, s.country, s.city, s.browser, s.os, s.device
    ORDER BY started_at DESC
    LIMIT ${limit} OFFSET ${offset}`,
    params
  );

  return results.map((r) => ({
    sessionId: r.session_id,
    country: r.country,
    city: r.city,
    browser: r.browser,
    os: r.os,
    device: r.device,
    pagesViewed: Number(r.pages_viewed),
    duration: r.duration ?? 0,
    startedAt:
      r.started_at instanceof Date
        ? r.started_at.toISOString()
        : String(r.started_at),
  }));
}

export interface SessionActivity {
  createdAt: string;
  urlPath: string;
  pageTitle: string | null;
  eventType: number;
  eventName: string | null;
  referrerDomain: string | null;
  visitId: string;
  eventData: Array<{ key: string; value: string }> | null;
}

/**
 * Get detailed activity for a specific session.
 */
export async function getSessionActivity(
  sessionId: string,
  websiteId: string
): Promise<SessionActivity[]> {
  const results = await rawQuery<{
    created_at: Date;
    url_path: string;
    page_title: string | null;
    event_type: number;
    event_name: string | null;
    referrer_domain: string | null;
    visit_id: string;
    event_data: Array<{ key: string; value: string }> | null;
  }>(
    `SELECT
      we.created_at,
      we.url_path,
      we.page_title,
      we.event_type,
      we.event_name,
      we.referrer_domain,
      we.visit_id,
      json_agg(
        json_build_object('key', ed.data_key, 'value', COALESCE(ed.string_value, ed.number_value::text))
      ) FILTER (WHERE ed.data_key IS NOT NULL) AS event_data
    FROM website_event we
    LEFT JOIN event_data ed ON we.event_id = ed.website_event_id
    WHERE we.session_id = {{sessionId::uuid}}
      AND we.website_id = {{websiteId::uuid}}
    GROUP BY we.event_id, we.created_at, we.url_path, we.page_title,
             we.event_type, we.event_name, we.referrer_domain, we.visit_id
    ORDER BY we.created_at ASC`,
    { sessionId, websiteId }
  );

  return results.map((r) => ({
    createdAt:
      r.created_at instanceof Date
        ? r.created_at.toISOString()
        : String(r.created_at),
    urlPath: r.url_path,
    pageTitle: r.page_title,
    eventType: r.event_type,
    eventName: r.event_name,
    referrerDomain: r.referrer_domain,
    visitId: r.visit_id,
    eventData: r.event_data,
  }));
}
