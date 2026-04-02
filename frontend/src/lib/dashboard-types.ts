/**
 * Dashboard configuration types.
 * Dashboards are stored in the `report` table with type = 'mantecato-dashboard'.
 */

export interface DashboardWidget {
  id: string;
  type: WidgetType;
  title: string;
  /** Grid position (12-column grid) */
  x: number;
  y: number;
  w: number;
  h: number;
  config: WidgetConfig;
}

export type WidgetType =
  | "metric"
  | "time-series"
  | "table"
  | "pie"
  | "bar"
  | "note"
  | "map"
  | "funnel"
  | "retention"
  | "comparison";

export interface MetricWidgetConfig {
  type: "metric";
  metric: "pageviews" | "visitors" | "visits" | "bounceRate" | "avgDuration" | "pagesPerVisit";
  siteId: string;
}

export interface TimeSeriesWidgetConfig {
  type: "time-series";
  metrics: string[];
  chartType: "area" | "line" | "bar";
  siteId: string;
}

export interface TableWidgetConfig {
  type: "table";
  dataSource: "pages" | "referrers" | "events" | "countries" | "browsers";
  limit: number;
  siteId: string;
}

export interface PieWidgetConfig {
  type: "pie";
  dataSource: "browsers" | "os" | "devices" | "countries";
  limit: number;
  siteId: string;
}

export interface BarWidgetConfig {
  type: "bar";
  dataSource: "pages" | "referrers" | "events" | "countries";
  limit: number;
  siteId: string;
}

export interface NoteWidgetConfig {
  type: "note";
  content: string;
}

export interface MapWidgetConfig {
  type: "map";
  siteId: string;
}

export interface FunnelWidgetConfig {
  type: "funnel";
  steps: string[];
  window: number; // hours
  siteId: string;
}

export interface RetentionWidgetConfig {
  type: "retention";
  period: "day" | "week" | "month";
  siteId: string;
}

export interface ComparisonWidgetConfig {
  type: "comparison";
  metric: "pageviews" | "visitors" | "visits" | "bounceRate" | "avgDuration" | "pagesPerVisit";
  siteId: string;
}

export type WidgetConfig =
  | MetricWidgetConfig
  | TimeSeriesWidgetConfig
  | TableWidgetConfig
  | PieWidgetConfig
  | BarWidgetConfig
  | NoteWidgetConfig
  | MapWidgetConfig
  | FunnelWidgetConfig
  | RetentionWidgetConfig
  | ComparisonWidgetConfig;

export interface DashboardConfig {
  version: 1;
  columns: 12;
  widgets: DashboardWidget[];
  dateRange: string;
}

export interface Dashboard {
  id: string;
  name: string;
  description: string;
  userId: string;
  websiteId: string;
  config: DashboardConfig;
  createdAt: string;
  updatedAt: string;
}

/** Default empty dashboard config */
export function createEmptyDashboard(): DashboardConfig {
  return {
    version: 1,
    columns: 12,
    widgets: [],
    dateRange: "30d",
  };
}

/** Default widget sizes by type */
export const DEFAULT_WIDGET_SIZES: Record<WidgetType, { w: number; h: number }> = {
  metric: { w: 3, h: 1 },
  "time-series": { w: 8, h: 3 },
  table: { w: 6, h: 4 },
  pie: { w: 4, h: 3 },
  bar: { w: 6, h: 3 },
  note: { w: 4, h: 2 },
  map: { w: 8, h: 4 },
  funnel: { w: 6, h: 3 },
  retention: { w: 8, h: 4 },
  comparison: { w: 3, h: 1 },
};

/** Widget type labels */
export const WIDGET_TYPE_LABELS: Record<WidgetType, string> = {
  metric: "Metric Card",
  "time-series": "Time Series Chart",
  table: "Data Table",
  pie: "Pie Chart",
  bar: "Bar Chart",
  note: "Text Note",
  map: "World Map",
  funnel: "Funnel",
  retention: "Retention Grid",
  comparison: "Comparison Card",
};
