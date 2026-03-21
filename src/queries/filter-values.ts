import { rawQuery, SESSION_COLUMNS } from "@/lib/queries";

/**
 * Valid columns for filter value lookups.
 * Must match VALID_FILTER_COLUMNS in queries.ts.
 */
const VALID_COLUMNS = new Set([
  "url_path",
  "page_title",
  "hostname",
  "referrer_domain",
  "utm_source",
  "utm_medium",
  "utm_campaign",
  "event_name",
  "tag",
  "browser",
  "os",
  "device",
  "country",
  "region",
  "city",
  "language",
  "screen",
]);

/**
 * Get distinct values for a column, scoped to a website and date range.
 * Used for autocomplete suggestions in the filter dialog.
 */
export async function getFilterValues(
  websiteId: string,
  column: string,
  startDate: Date,
  endDate: Date,
  search?: string,
  limit = 50
): Promise<string[]> {
  if (!VALID_COLUMNS.has(column)) return [];

  const isSessionCol = (SESSION_COLUMNS as readonly string[]).includes(column);
  const params: Record<string, unknown> = { websiteId, startDate, endDate };

  const searchClause = search
    ? `AND ${isSessionCol ? "s" : "we"}.${column} ILIKE {{search}}`
    : "";
  if (search) params.search = `%${search}%`;

  if (isSessionCol) {
    const results = await rawQuery<{ value: string }>(
      `SELECT DISTINCT s.${column} AS value
       FROM website_event we
       JOIN session s ON s.session_id = we.session_id
       WHERE we.website_id = {{websiteId::uuid}}
         AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
         AND s.${column} IS NOT NULL
         AND s.${column} != ''
         ${searchClause}
       ORDER BY value
       LIMIT ${limit}`,
      params
    );
    return results.map((r) => r.value);
  }

  const results = await rawQuery<{ value: string }>(
    `SELECT DISTINCT we.${column} AS value
     FROM website_event we
     WHERE we.website_id = {{websiteId::uuid}}
       AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
       AND we.${column} IS NOT NULL
       AND we.${column} != ''
       ${searchClause}
     ORDER BY value
     LIMIT ${limit}`,
    params
  );
  return results.map((r) => r.value);
}
