import { rawQuery } from "@/lib/queries";

export interface ActiveVisitor {
  sessionId: string;
  urlPath: string;
  country: string | null;
  city: string | null;
  browser: string | null;
  os: string | null;
  lastSeen: string;
}

/**
 * Get active visitors (sessions with events in the last 5 minutes).
 * Demographic fields live on the session table.
 */
export async function getActiveVisitors(
  websiteId: string
): Promise<{ count: number; visitors: ActiveVisitor[] }> {
  const results = await rawQuery<{
    session_id: string;
    url_path: string;
    country: string | null;
    city: string | null;
    browser: string | null;
    os: string | null;
    last_seen: Date;
  }>(
    `SELECT DISTINCT ON (we.session_id)
      we.session_id,
      we.url_path,
      s.country,
      s.city,
      s.browser,
      s.os,
      we.created_at AS last_seen
    FROM website_event we
    JOIN session s ON s.session_id = we.session_id
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at >= NOW() - INTERVAL '5 minutes'
    ORDER BY we.session_id, we.created_at DESC`,
    { websiteId }
  );

  return {
    count: results.length,
    visitors: results.map((r) => ({
      sessionId: r.session_id,
      urlPath: r.url_path,
      country: r.country,
      city: r.city,
      browser: r.browser,
      os: r.os,
      lastSeen:
        r.last_seen instanceof Date
          ? r.last_seen.toISOString()
          : String(r.last_seen),
    })),
  };
}

export interface RealtimeEvent {
  createdAt: string;
  urlPath: string;
  eventType: number;
  eventName: string | null;
  country: string | null;
  browser: string | null;
}

/**
 * Get recent events (last 30 seconds) for live stream.
 * Demographic fields live on the session table.
 */
export async function getRecentEvents(
  websiteId: string
): Promise<RealtimeEvent[]> {
  const results = await rawQuery<{
    created_at: Date;
    url_path: string;
    event_type: number;
    event_name: string | null;
    country: string | null;
    browser: string | null;
  }>(
    `SELECT
      we.created_at,
      we.url_path,
      we.event_type,
      we.event_name,
      s.country,
      s.browser
    FROM website_event we
    JOIN session s ON s.session_id = we.session_id
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at >= NOW() - INTERVAL '30 seconds'
    ORDER BY we.created_at DESC
    LIMIT 50`,
    { websiteId }
  );

  return results.map((r) => ({
    createdAt:
      r.created_at instanceof Date
        ? r.created_at.toISOString()
        : String(r.created_at),
    urlPath: r.url_path,
    eventType: r.event_type,
    eventName: r.event_name,
    country: r.country,
    browser: r.browser,
  }));
}

export interface CurrentPage {
  urlPath: string;
  visitors: number;
}

/**
 * Get currently viewed pages.
 */
export async function getCurrentPages(
  websiteId: string
): Promise<CurrentPage[]> {
  const results = await rawQuery<{
    url_path: string;
    visitors: bigint;
  }>(
    `SELECT
      url_path,
      COUNT(DISTINCT session_id)::bigint AS visitors
    FROM website_event
    WHERE website_id = {{websiteId::uuid}}
      AND created_at >= NOW() - INTERVAL '5 minutes'
      AND event_type = 1
    GROUP BY url_path
    ORDER BY visitors DESC
    LIMIT 20`,
    { websiteId }
  );

  return results.map((r) => ({
    urlPath: r.url_path,
    visitors: Number(r.visitors),
  }));
}
