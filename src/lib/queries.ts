import { prisma } from "./prisma";

type QueryParams = Record<string, unknown>;

/**
 * Execute raw SQL with named parameter substitution.
 * Parameters use {{name}} or {{name::type}} syntax.
 *
 * Example:
 *   rawQuery('SELECT * FROM website_event WHERE website_id = {{websiteId::uuid}}', { websiteId: '...' })
 *   becomes: SELECT * FROM website_event WHERE website_id = $1::uuid
 */
export async function rawQuery<T = Record<string, unknown>>(
  sql: string,
  data: QueryParams = {}
): Promise<T[]> {
  const params: unknown[] = [];

  const query = sql.replaceAll(
    /\{\{\s*(\w+)(::[\w[\]]+)?\s*\}\}/g,
    (_, name: string, type?: string) => {
      params.push(data[name]);
      return `$${params.length}${type ?? ""}`;
    }
  );

  return prisma.$queryRawUnsafe<T[]>(query, ...params);
}

/**
 * Execute a paged raw query. Returns { data, count, page, pageSize }.
 */
export async function pagedRawQuery<T = Record<string, unknown>>(
  sql: string,
  data: QueryParams,
  page = 1,
  pageSize = 50
): Promise<{ data: T[]; count: number; page: number; pageSize: number }> {
  const countSql = `SELECT COUNT(*) AS count FROM (${sql}) AS t`;
  const [{ count }] = await rawQuery<{ count: bigint }>(countSql, data);

  const pagedSql = `${sql} LIMIT ${pageSize} OFFSET ${(page - 1) * pageSize}`;
  const rows = await rawQuery<T>(pagedSql, data);

  return { data: rows, count: Number(count), page, pageSize };
}

/**
 * Build a date_trunc expression for time series grouping.
 */
export function getDateTrunc(granularity: string): string {
  const valid = ["minute", "hour", "day", "week", "month", "year"];
  if (!valid.includes(granularity)) return "date_trunc('day', we.created_at)";
  return `date_trunc('${granularity}', we.created_at)`;
}

/**
 * Session columns that require a JOIN on the session table.
 */
export const SESSION_COLUMNS = [
  "browser",
  "os",
  "device",
  "screen",
  "language",
  "country",
  "region",
  "city",
] as const;

export type SessionColumn = (typeof SESSION_COLUMNS)[number];

export interface Filter {
  column: string;
  operator: "eq" | "neq" | "contains" | "starts_with";
  value: string;
}

/**
 * Build dynamic WHERE clauses from filters.
 */
export function buildFilterSQL(filters: Filter[]): {
  sql: string;
  params: Record<string, unknown>;
  needsSessionJoin: boolean;
} {
  const clauses: string[] = [];
  const params: Record<string, unknown> = {};
  let needsSessionJoin = false;

  for (const filter of filters) {
    const paramName = `filter_${filter.column}`;
    const isSessionCol = (SESSION_COLUMNS as readonly string[]).includes(
      filter.column
    );

    if (isSessionCol) {
      needsSessionJoin = true;
    }

    const prefix = isSessionCol ? "s" : "we";

    switch (filter.operator) {
      case "eq":
        clauses.push(`${prefix}.${filter.column} = {{${paramName}}}`);
        params[paramName] = filter.value;
        break;
      case "neq":
        clauses.push(`${prefix}.${filter.column} != {{${paramName}}}`);
        params[paramName] = filter.value;
        break;
      case "contains":
        clauses.push(`${prefix}.${filter.column} LIKE {{${paramName}}}`);
        params[paramName] = `%${filter.value}%`;
        break;
      case "starts_with":
        clauses.push(`${prefix}.${filter.column} LIKE {{${paramName}}}`);
        params[paramName] = `${filter.value}%`;
        break;
    }
  }

  return {
    sql: clauses.length > 0 ? `AND ${clauses.join(" AND ")}` : "",
    params,
    needsSessionJoin,
  };
}
