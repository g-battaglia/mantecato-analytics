import { useQuery } from "@tanstack/react-query";
import { MetricCard } from "@/components/data/MetricCard";
import { AreaChart } from "@/components/charts/AreaChart";
import { PieChart } from "@/components/charts/PieChart";
import { BarChart } from "@/components/charts/BarChart";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CHART_COLORS } from "@/lib/constants";
import { formatNumber, formatPercent, percentChange } from "@/lib/format";
import { cn } from "@/lib/utils";
import { apiFetch } from "@/lib/api";
import type {
  DashboardWidget,
  MetricWidgetConfig,
  TimeSeriesWidgetConfig,
  TableWidgetConfig,
  PieWidgetConfig,
  BarWidgetConfig,
  NoteWidgetConfig,
  MapWidgetConfig,
  FunnelWidgetConfig,
  RetentionWidgetConfig,
  ComparisonWidgetConfig,
} from "@/lib/dashboard-types";

interface WidgetRendererProps {
  widget: DashboardWidget;
  dateRange: string;
}

// Main dispatcher that renders the correct widget sub-component based on config type
export function WidgetRenderer({ widget, dateRange }: WidgetRendererProps) {
  switch (widget.config.type) {
    case "metric":
      return <MetricWidget widget={widget} config={widget.config} dateRange={dateRange} />;
    case "time-series":
      return <TimeSeriesWidget widget={widget} config={widget.config} dateRange={dateRange} />;
    case "table":
      return <TableWidget widget={widget} config={widget.config} dateRange={dateRange} />;
    case "pie":
      return <PieWidget widget={widget} config={widget.config} dateRange={dateRange} />;
    case "bar":
      return <BarWidget widget={widget} config={widget.config} dateRange={dateRange} />;
    case "note":
      return <NoteWidget widget={widget} config={widget.config} />;
    case "map":
      return <MapWidget widget={widget} config={widget.config} dateRange={dateRange} />;
    case "funnel":
      return <FunnelWidget widget={widget} config={widget.config} dateRange={dateRange} />;
    case "retention":
      return <RetentionWidget widget={widget} config={widget.config} dateRange={dateRange} />;
    case "comparison":
      return <ComparisonWidget widget={widget} config={widget.config} dateRange={dateRange} />;
    default:
      return (
        <Card>
          <CardContent className="flex items-center justify-center p-6 text-sm text-muted-foreground">
            Unknown widget type
          </CardContent>
        </Card>
      );
  }
}

// --- Metric Widget ---

// Displays a single KPI metric (pageviews, visitors, bounce rate, etc.)
function MetricWidget({
  widget,
  config,
  dateRange,
}: {
  widget: DashboardWidget;
  config: MetricWidgetConfig;
  dateRange: string;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["widget-metric", config.siteId, config.metric, dateRange],
    queryFn: async () => {
      const res = await apiFetch(
        `/api/sites/${config.siteId}/stats?range=${dateRange}&section=metrics`
      );
      if (!res.ok) throw new Error("Failed");
      return res.json();
    },
  });

  // Maps metric names to their key, display format, and optional computed value
  const metricMap: Record<string, { key: string; format: "number" | "percent" | "duration"; compute?: (s: Record<string, number>) => number }> = {
    pageviews: { key: "pageviews", format: "number" },
    visitors: { key: "visitors", format: "number" },
    visits: { key: "visits", format: "number" },
    bounceRate: {
      key: "bounceRate",
      format: "percent",
      compute: (s) => (s.visits > 0 ? (s.bounces / s.visits) * 100 : 0),
    },
    avgDuration: {
      key: "avgDuration",
      format: "duration",
      compute: (s) => (s.visits > 0 ? s.totaltime / s.visits : 0),
    },
    pagesPerVisit: {
      key: "pagesPerVisit",
      format: "number",
      compute: (s) => (s.visits > 0 ? s.pageviews / s.visits : 0),
    },
  };

  const m = metricMap[config.metric];
  const value = data
    ? m?.compute
      ? m.compute(data)
      : (data[m?.key ?? config.metric] as number)
    : null;

  return (
    <MetricCard
      label={widget.title}
      value={value ?? null}
      format={m?.format ?? "number"}
      loading={isLoading}
    />
  );
}

// --- Time Series Widget ---

// Renders a line/area chart over time for the configured metrics
function TimeSeriesWidget({
  widget,
  config,
  dateRange,
}: {
  widget: DashboardWidget;
  config: TimeSeriesWidgetConfig;
  dateRange: string;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["widget-timeseries", config.siteId, dateRange],
    queryFn: async () => {
      const res = await apiFetch(
        `/api/sites/${config.siteId}/stats?range=${dateRange}&section=timeseries`
      );
      if (!res.ok) throw new Error("Failed");
      return res.json();
    },
  });

  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{widget.title}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-[200px] w-full" />
        ) : data?.length > 0 ? (
          <AreaChart
            data={data}
            xKey="time"
            yKeys={config.metrics.length > 0 ? config.metrics : ["pageviews"]}
            height={200}
          />
        ) : (
          <p className="py-8 text-center text-xs text-muted-foreground">No data</p>
        )}
      </CardContent>
    </Card>
  );
}

// --- Table Widget ---

// Renders a list of rows from a stats section (pages, referrers, events, etc.)
function TableWidget({
  widget,
  config,
  dateRange,
}: {
  widget: DashboardWidget;
  config: TableWidgetConfig;
  dateRange: string;
}) {
  // Maps friendly data source names to API section parameter values
  const sectionMap: Record<string, string> = {
    pages: "pages",
    referrers: "referrers",
    events: "events",
    countries: "countries",
    browsers: "browsers",
  };

  const { data, isLoading } = useQuery({
    queryKey: ["widget-table", config.siteId, config.dataSource, dateRange],
    queryFn: async () => {
      const section = sectionMap[config.dataSource] ?? "pages";
      const res = await apiFetch(
        `/api/sites/${config.siteId}/stats?range=${dateRange}&section=${section}`
      );
      if (!res.ok) throw new Error("Failed");
      return res.json();
    },
  });

  // Slice to the configured row limit
  const rows = (data as Record<string, unknown>[] | undefined)?.slice(0, config.limit) ?? [];

  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{widget.title}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: Math.min(config.limit, 5) }).map((_, i) => (
              <Skeleton key={i} className="h-6 w-full" />
            ))}
          </div>
        ) : rows.length > 0 ? (
          <div className="space-y-1">
            {rows.map((row, i) => {
              // Pick the best available label field depending on data source
              const label = String(
                row.urlPath ?? row.referrerDomain ?? row.eventName ?? row.country ?? row.value ?? `Row ${i}`
              );
              // Pick the best available metric field
              const metric = Number(
                row.views ?? row.visitors ?? row.count ?? row.pageviews ?? 0
              );
              return (
                <div key={i} className="flex items-center justify-between py-1 text-sm">
                  <span className="truncate text-xs">{label}</span>
                  <span className="tabular-nums font-medium">{metric.toLocaleString()}</span>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="py-8 text-center text-xs text-muted-foreground">No data</p>
        )}
      </CardContent>
    </Card>
  );
}

// --- Pie Widget ---

// Renders a pie chart for breakdown data (browsers, OS, devices, countries)
function PieWidget({
  widget,
  config,
  dateRange,
}: {
  widget: DashboardWidget;
  config: PieWidgetConfig;
  dateRange: string;
}) {
  const sectionMap: Record<string, string> = {
    browsers: "browsers",
    os: "os",
    devices: "devices",
    countries: "countries",
  };

  const { data, isLoading } = useQuery({
    queryKey: ["widget-pie", config.siteId, config.dataSource, dateRange],
    queryFn: async () => {
      const section = sectionMap[config.dataSource] ?? "browsers";
      const res = await apiFetch(
        `/api/sites/${config.siteId}/stats?range=${dateRange}&section=${section}`
      );
      if (!res.ok) throw new Error("Failed");
      return res.json();
    },
  });

  // Transform API rows into name/value pairs for the PieChart component
  const chartData = (data as Record<string, unknown>[] | undefined)
    ?.slice(0, config.limit)
    .map((row) => ({
      name: String(row.value ?? row.country ?? "Unknown"),
      value: Number(row.visitors ?? row.pageviews ?? 0),
    })) ?? [];

  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{widget.title}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="mx-auto h-[180px] w-[180px] rounded-full" />
        ) : chartData.length > 0 ? (
          <PieChart data={chartData} height={200} />
        ) : (
          <p className="py-8 text-center text-xs text-muted-foreground">No data</p>
        )}
      </CardContent>
    </Card>
  );
}

// --- Bar Widget ---

// Renders a horizontal bar chart for ranked data
function BarWidget({
  widget,
  config,
  dateRange,
}: {
  widget: DashboardWidget;
  config: BarWidgetConfig;
  dateRange: string;
}) {
  const sectionMap: Record<string, string> = {
    pages: "pages",
    referrers: "referrers",
    events: "events",
    countries: "countries",
  };

  const { data, isLoading } = useQuery({
    queryKey: ["widget-bar", config.siteId, config.dataSource, dateRange],
    queryFn: async () => {
      const section = sectionMap[config.dataSource] ?? "pages";
      const res = await apiFetch(
        `/api/sites/${config.siteId}/stats?range=${dateRange}&section=${section}`
      );
      if (!res.ok) throw new Error("Failed");
      return res.json();
    },
  });

  // Transform API rows into name/value pairs for the BarChart component
  const chartData = (data as Record<string, unknown>[] | undefined)
    ?.slice(0, config.limit)
    .map((row) => ({
      name: String(row.urlPath ?? row.referrerDomain ?? row.eventName ?? row.country ?? "Unknown"),
      value: Number(row.views ?? row.visitors ?? row.count ?? row.pageviews ?? 0),
    })) ?? [];

  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{widget.title}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-[200px] w-full" />
        ) : chartData.length > 0 ? (
          <BarChart
            data={chartData}
            yKeys={["value"]}
            labels={{ value: widget.title }}
            xKey="name"
            height={200}
            horizontal
          />
        ) : (
          <p className="py-8 text-center text-xs text-muted-foreground">No data</p>
        )}
      </CardContent>
    </Card>
  );
}

// --- Note Widget ---

// Displays a freeform text note (no data fetching)
function NoteWidget({
  widget,
  config,
}: {
  widget: DashboardWidget;
  config: NoteWidgetConfig;
}) {
  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{widget.title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="whitespace-pre-wrap text-sm text-muted-foreground">
          {config.content || "Empty note"}
        </p>
      </CardContent>
    </Card>
  );
}

// --- Map Widget ---

// Renders a country breakdown as a horizontal bar list with proportional fills
function MapWidget({
  widget,
  config,
  dateRange,
}: {
  widget: DashboardWidget;
  config: MapWidgetConfig;
  dateRange: string;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["widget-map", config.siteId, dateRange],
    queryFn: async () => {
      const res = await apiFetch(
        `/api/sites/${config.siteId}/geo?range=${dateRange}`
      );
      if (!res.ok) throw new Error("Failed");
      return res.json();
    },
  });

  const rows = (data as Record<string, unknown>[] | undefined) ?? [];

  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{widget.title}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-[200px] w-full" />
        ) : rows.length > 0 ? (
          <div className="space-y-1">
            {rows.slice(0, 10).map((row, i) => {
              const country = String(row.country ?? "Unknown");
              const visitors = Number(row.visitors ?? 0);
              // Scale bar width relative to the top country
              const maxVisitors = Number(rows[0]?.visitors ?? 1);
              const pct = (visitors / maxVisitors) * 100;
              return (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="w-8 shrink-0 text-right tabular-nums font-medium">
                    {country}
                  </span>
                  <div className="flex-1 h-4 rounded bg-muted overflow-hidden">
                    <div
                      className="h-full rounded"
                      style={{
                        width: `${pct}%`,
                        backgroundColor: CHART_COLORS[0],
                        opacity: 0.7,
                      }}
                    />
                  </div>
                  <span className="w-12 shrink-0 text-right tabular-nums">
                    {visitors.toLocaleString()}
                  </span>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="py-8 text-center text-xs text-muted-foreground">No data</p>
        )}
      </CardContent>
    </Card>
  );
}

// --- Funnel Widget ---

// Renders a funnel visualization showing step-by-step conversion and drop-off
function FunnelWidget({
  widget,
  config,
  dateRange,
}: {
  widget: DashboardWidget;
  config: FunnelWidgetConfig;
  dateRange: string;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["widget-funnel", config.siteId, config.steps, config.window, dateRange],
    queryFn: async () => {
      const params = new URLSearchParams({
        range: dateRange,
        window: String(config.window),
      });
      config.steps.forEach((s) => params.append("step", s));
      const res = await apiFetch(
        `/api/sites/${config.siteId}/funnels?${params}`
      );
      if (!res.ok) throw new Error("Failed");
      return res.json();
    },
    // Only fetch when there are at least 2 funnel steps defined
    enabled: config.steps.length >= 2,
  });

  interface FunnelStep {
    step: number;
    name: string;
    visitors: number;
    dropoff: number;
    conversionRate: number;
  }

  const steps = (data as FunnelStep[] | undefined) ?? [];

  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{widget.title}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-[200px] w-full" />
        ) : steps.length > 0 ? (
          <div className="space-y-2">
            {steps.map((step, i) => {
              // Scale bar relative to first step (100%)
              const maxVisitors = steps[0]?.visitors ?? 1;
              const pct = (step.visitors / maxVisitors) * 100;
              return (
                <div key={i} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="truncate font-mono">
                      {step.step}. {step.name}
                    </span>
                    <span className="shrink-0 tabular-nums">
                      {step.visitors.toLocaleString()}{" "}
                      <span className="text-muted-foreground">
                        ({pct.toFixed(0)}%)
                      </span>
                    </span>
                  </div>
                  <div className="h-5 rounded bg-muted overflow-hidden">
                    <div
                      className="h-full rounded transition-all"
                      style={{
                        width: `${pct}%`,
                        backgroundColor: CHART_COLORS[i % CHART_COLORS.length],
                        opacity: 0.7,
                      }}
                    />
                  </div>
                  {/* Show drop-off count between steps */}
                  {i < steps.length - 1 && step.dropoff > 0 && (
                    <p className="text-[10px] text-muted-foreground text-right">
                      -{step.dropoff.toLocaleString()} dropped
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <p className="py-8 text-center text-xs text-muted-foreground">
            {config.steps.length < 2 ? "Add at least 2 steps" : "No data"}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// --- Retention Widget ---

// Renders a cohort retention table with color-coded percentage cells
function RetentionWidget({
  widget,
  config,
  dateRange,
}: {
  widget: DashboardWidget;
  config: RetentionWidgetConfig;
  dateRange: string;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["widget-retention", config.siteId, config.period, dateRange],
    queryFn: async () => {
      const res = await apiFetch(
        `/api/sites/${config.siteId}/retention?range=${dateRange}&period=${config.period}`
      );
      if (!res.ok) throw new Error("Failed");
      return res.json();
    },
  });

  interface RetentionRow {
    cohort: string;
    totalUsers: number;
    periods: number[];
  }

  const rows = (data as RetentionRow[] | undefined) ?? [];

  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{widget.title}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-[200px] w-full" />
        ) : rows.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-[10px]">
              <thead>
                <tr>
                  <th className="text-left px-1 py-0.5 font-medium text-muted-foreground">
                    Cohort
                  </th>
                  <th className="text-right px-1 py-0.5 font-medium text-muted-foreground">
                    Users
                  </th>
                  {/* Column headers use period prefix: D/W/M */}
                  {rows[0]?.periods.map((_, i) => (
                    <th
                      key={i}
                      className="text-center px-1 py-0.5 font-medium text-muted-foreground"
                    >
                      {config.period === "day" ? `D${i}` : config.period === "week" ? `W${i}` : `M${i}`}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 8).map((row, ri) => (
                  <tr key={ri}>
                    <td className="px-1 py-0.5 whitespace-nowrap text-muted-foreground">
                      {row.cohort}
                    </td>
                    <td className="px-1 py-0.5 text-right tabular-nums">
                      {row.totalUsers}
                    </td>
                    {row.periods.map((pct, pi) => (
                      <td
                        key={pi}
                        className="px-1 py-0.5 text-center tabular-nums"
                        style={{
                          // Color intensity proportional to retention percentage
                          backgroundColor:
                            pct > 0
                              ? `color-mix(in srgb, ${CHART_COLORS[0]} ${Math.min(pct, 100)}%, transparent)`
                              : undefined,
                        }}
                      >
                        {pct > 0 ? `${pct.toFixed(0)}%` : ""}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="py-8 text-center text-xs text-muted-foreground">No data</p>
        )}
      </CardContent>
    </Card>
  );
}

// --- Comparison Widget ---

// Displays a metric card comparing current vs previous period with change percentage
function ComparisonWidget({
  widget,
  config,
  dateRange,
}: {
  widget: DashboardWidget;
  config: ComparisonWidgetConfig;
  dateRange: string;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["widget-comparison", config.siteId, config.metric, dateRange],
    queryFn: async () => {
      const res = await apiFetch(
        `/api/sites/${config.siteId}/compare?range=${dateRange}`
      );
      if (!res.ok) throw new Error("Failed");
      return res.json();
    },
  });

  // Same metric map as MetricWidget — maps metric names to keys and formats
  const metricMap: Record<string, { key: string; format: "number" | "percent" | "duration"; compute?: (s: Record<string, number>) => number }> = {
    pageviews: { key: "pageviews", format: "number" },
    visitors: { key: "visitors", format: "number" },
    visits: { key: "visits", format: "number" },
    bounceRate: {
      key: "bounceRate",
      format: "percent",
      compute: (s) => (s.visits > 0 ? (s.bounces / s.visits) * 100 : 0),
    },
    avgDuration: {
      key: "avgDuration",
      format: "duration",
      compute: (s) => (s.visits > 0 ? s.totaltime / s.visits : 0),
    },
    pagesPerVisit: {
      key: "pagesPerVisit",
      format: "number",
      compute: (s) => (s.visits > 0 ? s.pageviews / s.visits : 0),
    },
  };

  const m = metricMap[config.metric];

  let currentValue: number | null = null;
  let previousValue: number | null = null;

  // Extract current and previous period values from the API response
  if (data) {
    const current = data.current as Record<string, number> | undefined;
    const previous = data.previous as Record<string, number> | undefined;
    if (current) {
      currentValue = m?.compute ? m.compute(current) : (current[m?.key ?? config.metric] ?? null);
    }
    if (previous) {
      previousValue = m?.compute ? m.compute(previous) : (previous[m?.key ?? config.metric] ?? null);
    }
  }

  const change =
    currentValue != null && previousValue != null
      ? percentChange(currentValue, previousValue)
      : null;

  return (
    <MetricCard
      label={widget.title}
      value={currentValue}
      previousValue={previousValue ?? undefined}
      format={m?.format ?? "number"}
      loading={isLoading}
    />
  );
}
