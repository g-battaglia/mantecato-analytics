/**
 * Shared type definitions extracted from server-only modules.
 * These types are needed by both the frontend and backend but
 * cannot be imported from server-only files in a Vite SPA.
 */

export interface Filter {
  column: string;
  operator: "eq" | "neq" | "contains" | "not_contains" | "starts_with" | "not_starts_with";
  value: string;
}

export interface ScheduledExportConfig {
  websiteId: string;
  dataSource: "overview" | "pages" | "referrers" | "events" | "sessions" | "devices" | "geo";
  format: "csv" | "json" | "xlsx";
  dateRange: string;
  schedule: "daily" | "weekly" | "monthly";
  weekDay?: number;
  monthDay?: number;
  enabled: boolean;
  lastRunAt?: string | null;
  nextRunAt?: string | null;
}

export interface ScheduledExport {
  id: string;
  name: string;
  description: string;
  userId: string;
  websiteId: string;
  config: ScheduledExportConfig;
  createdAt: string;
  updatedAt: string;
}
