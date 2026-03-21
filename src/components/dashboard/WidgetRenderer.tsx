"use client";

import { useQuery } from "@tanstack/react-query";
import { MetricCard } from "@/components/data/MetricCard";
import { AreaChart } from "@/components/charts/AreaChart";
import { PieChart } from "@/components/charts/PieChart";
import { BarChart } from "@/components/charts/BarChart";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type {
  DashboardWidget,
  MetricWidgetConfig,
  TimeSeriesWidgetConfig,
  TableWidgetConfig,
  PieWidgetConfig,
  BarWidgetConfig,
  NoteWidgetConfig,
} from "@/lib/dashboard-types";

interface WidgetRendererProps {
  widget: DashboardWidget;
  dateRange: string;
}

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
      const res = await fetch(
        `/api/sites/${config.siteId}/stats?range=${dateRange}&section=metrics`
      );
      if (!res.ok) throw new Error("Failed");
      return res.json();
    },
  });

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
      const res = await fetch(
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

function TableWidget({
  widget,
  config,
  dateRange,
}: {
  widget: DashboardWidget;
  config: TableWidgetConfig;
  dateRange: string;
}) {
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
      const res = await fetch(
        `/api/sites/${config.siteId}/stats?range=${dateRange}&section=${section}`
      );
      if (!res.ok) throw new Error("Failed");
      return res.json();
    },
  });

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
              const label = String(
                row.urlPath ?? row.referrerDomain ?? row.eventName ?? row.country ?? row.value ?? `Row ${i}`
              );
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
      const res = await fetch(
        `/api/sites/${config.siteId}/stats?range=${dateRange}&section=${section}`
      );
      if (!res.ok) throw new Error("Failed");
      return res.json();
    },
  });

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
      const res = await fetch(
        `/api/sites/${config.siteId}/stats?range=${dateRange}&section=${section}`
      );
      if (!res.ok) throw new Error("Failed");
      return res.json();
    },
  });

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
