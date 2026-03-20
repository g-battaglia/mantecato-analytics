/** Event type constants matching Umami's schema */
export const EVENT_TYPE = {
  PAGEVIEW: 1,
  CUSTOM_EVENT: 2,
} as const;

/** Report type namespaces for Mantecato-specific data in the report table */
export const REPORT_TYPE = {
  DASHBOARD: "mantecato-dashboard",
  SAVED_VIEW: "mantecato-saved-view",
  ANNOTATION: "mantecato-annotation",
} as const;

/** Default date range preset */
export const DEFAULT_DATE_RANGE = "30d" as const;

/** Default number of rows in tables */
export const DEFAULT_PAGE_SIZE = 10;

/** Realtime polling interval (ms) */
export const REALTIME_INTERVAL = 5_000;

/** TanStack Query stale times */
export const STALE_TIME = {
  STANDARD: 60_000, // 1 minute
  REALTIME: 5_000, // 5 seconds
  STATIC: 300_000, // 5 minutes (for things that rarely change)
} as const;

/** Chart color palette — works in both light and dark mode, colorblind-safe */
export const CHART_COLORS = [
  "hsl(221, 83%, 53%)", // blue
  "hsl(142, 71%, 45%)", // green
  "hsl(38, 92%, 50%)", // amber
  "hsl(0, 84%, 60%)", // red
  "hsl(271, 81%, 56%)", // purple
  "hsl(189, 94%, 43%)", // cyan
  "hsl(25, 95%, 53%)", // orange
  "hsl(330, 81%, 60%)", // pink
] as const;

/** Date range preset definitions */
export const DATE_RANGE_PRESETS = {
  today: { label: "Today" },
  yesterday: { label: "Yesterday" },
  "24h": { label: "Last 24 hours" },
  "7d": { label: "Last 7 days" },
  "14d": { label: "Last 14 days" },
  "30d": { label: "Last 30 days" },
  "60d": { label: "Last 60 days" },
  "90d": { label: "Last 90 days" },
  "6m": { label: "Last 6 months" },
  "12m": { label: "Last 12 months" },
  this_week: { label: "This week" },
  last_week: { label: "Last week" },
  this_month: { label: "This month" },
  last_month: { label: "Last month" },
  this_quarter: { label: "This quarter" },
  last_quarter: { label: "Last quarter" },
  this_year: { label: "This year" },
  last_year: { label: "Last year" },
  all: { label: "All time" },
  custom: { label: "Custom range" },
} as const;

export type DateRangePreset = keyof typeof DATE_RANGE_PRESETS;

/** Comparison mode definitions */
export const COMPARISON_MODES = {
  previous_period: { label: "Previous period" },
  previous_year: { label: "Previous year" },
  custom: { label: "Custom" },
  none: { label: "None" },
} as const;

export type ComparisonMode = keyof typeof COMPARISON_MODES;

/** Granularity options */
export const GRANULARITY_OPTIONS = {
  auto: { label: "Auto" },
  hour: { label: "Hourly" },
  day: { label: "Daily" },
  week: { label: "Weekly" },
  month: { label: "Monthly" },
} as const;

export type Granularity = keyof typeof GRANULARITY_OPTIONS;

/** Available filter columns with metadata */
export const FILTER_COLUMNS = [
  { column: "url_path", label: "URL Path", type: "text" as const },
  { column: "page_title", label: "Page Title", type: "text" as const },
  { column: "hostname", label: "Hostname", type: "select" as const },
  { column: "referrer_domain", label: "Referrer", type: "text" as const },
  { column: "utm_source", label: "UTM Source", type: "select" as const },
  { column: "utm_medium", label: "UTM Medium", type: "select" as const },
  { column: "utm_campaign", label: "UTM Campaign", type: "select" as const },
  { column: "event_name", label: "Event Name", type: "select" as const },
  { column: "tag", label: "Tag", type: "text" as const },
  { column: "browser", label: "Browser", type: "select" as const },
  { column: "os", label: "OS", type: "select" as const },
  { column: "device", label: "Device", type: "select" as const },
  { column: "country", label: "Country", type: "select" as const },
  { column: "region", label: "Region", type: "select" as const },
  { column: "city", label: "City", type: "select" as const },
  { column: "language", label: "Language", type: "select" as const },
  { column: "screen", label: "Screen", type: "select" as const },
] as const;

export type FilterColumn = (typeof FILTER_COLUMNS)[number]["column"];

/** Filter operators */
export const FILTER_OPERATORS = {
  eq: { label: "is", symbol: "=" },
  neq: { label: "is not", symbol: "≠" },
  contains: { label: "contains", symbol: "∋" },
  starts_with: { label: "starts with", symbol: "^" },
} as const;

export type FilterOperator = keyof typeof FILTER_OPERATORS;
