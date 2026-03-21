/**
 * Shared helpers for CLI and MCP server.
 * Provides site resolution, date parsing, filter parsing, output formatting.
 */
import { rawQuery, type Filter } from "@/lib/queries";
import { resolveDateRange, resolveGranularity, type DateRange } from "@/lib/date";
import { formatDuration, formatPercent } from "@/lib/format";
import type { DateRangePreset, Granularity } from "@/lib/constants";

// ---------------------------------------------------------------------------
// Site resolution
// ---------------------------------------------------------------------------

export interface SiteInfo {
  websiteId: string;
  name: string;
  domain: string;
  createdAt: string;
}

export async function listSites(): Promise<SiteInfo[]> {
  return rawQuery<SiteInfo>(
    `SELECT website_id AS "websiteId", name, domain, created_at AS "createdAt"
     FROM website WHERE deleted_at IS NULL ORDER BY name`
  );
}

export async function resolveSiteId(nameOrId: string): Promise<string> {
  const sites = await listSites();
  const lower = nameOrId.toLowerCase();
  const exact = sites.find(
    (s) =>
      s.websiteId === nameOrId ||
      s.name.toLowerCase() === lower ||
      s.domain.toLowerCase() === lower
  );
  if (exact) return exact.websiteId;
  const partial = sites.find(
    (s) =>
      s.name.toLowerCase().includes(lower) ||
      s.domain.toLowerCase().includes(lower)
  );
  if (partial) return partial.websiteId;
  const available = sites.map((s) => `${s.name} (${s.domain})`).join(", ");
  throw new Error(`Site "${nameOrId}" not found. Available: ${available}`);
}

// ---------------------------------------------------------------------------
// Date range helpers
// ---------------------------------------------------------------------------

export function parseDateArgs(
  period?: string,
  start?: string,
  end?: string
): DateRange {
  if (start && end) {
    return { startDate: new Date(start), endDate: new Date(end) };
  }
  if (start) {
    return { startDate: new Date(start), endDate: new Date() };
  }
  const preset = (period || "30d") as DateRangePreset;
  const range = resolveDateRange(preset);
  if (!range) {
    const now = new Date();
    return {
      startDate: new Date(now.getTime() - 365 * 86_400_000),
      endDate: now,
    };
  }
  return range;
}

export function resolveGranularityArg(
  granularity: string | undefined,
  range: DateRange
): string {
  const g = (granularity || "auto") as Granularity;
  return resolveGranularity(g, range);
}

// ---------------------------------------------------------------------------
// Filter parsing
// ---------------------------------------------------------------------------

export function parseFilterArgs(filterStrs: string[]): Filter[] {
  if (!filterStrs || filterStrs.length === 0) return [];
  return filterStrs.map((f) => {
    const idx1 = f.indexOf(":");
    if (idx1 === -1)
      throw new Error(
        `Invalid filter: "${f}". Format: column:operator:value`
      );
    const column = f.slice(0, idx1);
    const rest = f.slice(idx1 + 1);
    const idx2 = rest.indexOf(":");
    if (idx2 === -1)
      throw new Error(
        `Invalid filter: "${f}". Format: column:operator:value`
      );
    const operator = rest.slice(0, idx2) as Filter["operator"];
    const value = rest.slice(idx2 + 1);
    return { column, operator, value };
  });
}

// ---------------------------------------------------------------------------
// Output formatting
// ---------------------------------------------------------------------------

export type OutputFormat = "json" | "table" | "csv";

/**
 * Format query results for display.
 * - json: pretty-printed JSON
 * - table: aligned columns
 * - csv: comma-separated
 */
export function formatOutput(
  data: unknown,
  format: OutputFormat,
  opts?: { title?: string }
): string {
  if (format === "json") {
    return JSON.stringify(data, null, 2);
  }

  // Single-object (stats, summary) → key-value display
  if (data && typeof data === "object" && !Array.isArray(data)) {
    const entries = Object.entries(data as Record<string, unknown>);
    if (format === "csv") {
      return (
        "key,value\n" + entries.map(([k, v]) => `${k},${v ?? ""}`).join("\n")
      );
    }
    const maxK = Math.max(...entries.map(([k]) => k.length), 4);
    const lines: string[] = [];
    if (opts?.title) lines.push(`\n${opts.title}\n${"=".repeat(opts.title.length)}`);
    for (const [k, v] of entries) {
      lines.push(`  ${k.padEnd(maxK)}  ${formatValue(v)}`);
    }
    return lines.join("\n");
  }

  // Array of objects → table
  if (!Array.isArray(data) || data.length === 0) {
    return format === "csv" ? "" : "No data";
  }

  const rows = data as Record<string, unknown>[];
  const keys = Object.keys(rows[0]);

  if (format === "csv") {
    const header = keys.join(",");
    const csvRows = rows.map((r) =>
      keys
        .map((k) => {
          const s = String(r[k] ?? "");
          return s.includes(",") || s.includes('"') || s.includes("\n")
            ? `"${s.replace(/"/g, '""')}"`
            : s;
        })
        .join(",")
    );
    return [header, ...csvRows].join("\n");
  }

  // Table format
  const widths = keys.map((k) => {
    const vals = rows.map((r) => String(formatValue(r[k])).length);
    return Math.min(Math.max(k.length, ...vals), 60);
  });

  const lines: string[] = [];
  if (opts?.title) lines.push(`\n${opts.title}\n${"=".repeat(opts.title.length)}`);
  lines.push(keys.map((k, i) => k.padEnd(widths[i])).join("  "));
  lines.push(widths.map((w) => "─".repeat(w)).join("  "));
  for (const r of rows) {
    lines.push(
      keys
        .map((k, i) => {
          const s = String(formatValue(r[k]));
          return s.length > 60 ? s.slice(0, 57) + "..." : s.padEnd(widths[i]);
        })
        .join("  ")
    );
  }
  lines.push(`\n(${rows.length} rows)`);
  return lines.join("\n");
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return "-";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return "-";
    return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(2);
  }
  if (v instanceof Date) return v.toISOString();
  if (Array.isArray(v)) return v.join(" → ");
  return String(v);
}

// ---------------------------------------------------------------------------
// Stats post-processing
// ---------------------------------------------------------------------------

/**
 * Compute derived stats (bounce rate, avg duration, pages/visit) from raw DB row.
 */
export function computeDerivedStats(raw: {
  pageviews: number;
  visitors: number;
  visits: number;
  bounces: number;
  totaltime: number;
}) {
  const bounceRate =
    raw.visits > 0 ? formatPercent((raw.bounces / raw.visits) * 100) : "0%";
  const avgDuration =
    raw.visits > 0
      ? formatDuration(Math.round(raw.totaltime / raw.visits))
      : "0s";
  const pagesPerVisit =
    raw.visits > 0 ? (raw.pageviews / raw.visits).toFixed(2) : "0";
  return {
    pageviews: raw.pageviews,
    visitors: raw.visitors,
    visits: raw.visits,
    bounceRate,
    avgDuration,
    pagesPerVisit,
  };
}
