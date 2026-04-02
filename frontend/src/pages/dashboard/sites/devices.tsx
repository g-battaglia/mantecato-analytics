
import { useMemo, useState } from "react";
import { type ColumnDef } from "@tanstack/react-table";
import { BarChart3, PieChartIcon } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/data/DataTable";
import { DonutChart } from "@/components/charts/PieChart";
import { useSiteQuery } from "@/hooks/use-site-query";
import { formatPercent } from "@/lib/format";
import { CHART_COLORS } from "@/lib/constants";

interface DeviceRow {
  value: string;
  visitors: number;
  pageviews: number;
  percentage: number;
}

interface DevicesData {
  browsers: DeviceRow[];
  os: DeviceRow[];
  devices: DeviceRow[];
  screens: DeviceRow[];
  languages: DeviceRow[];
}

function deviceColumns(label: string): ColumnDef<DeviceRow>[] {
  return [
    { accessorKey: "value", header: label, enableSorting: false },
    {
      accessorKey: "visitors",
      header: () => <span className="flex justify-end">Visitors</span>,
      cell: ({ getValue }) => (
        <span className="flex justify-end tabular-nums">
          {(getValue() as number).toLocaleString()}
        </span>
      ),
    },
    {
      accessorKey: "percentage",
      header: () => <span className="flex justify-end">%</span>,
      cell: ({ getValue }) => (
        <span className="flex justify-end tabular-nums">
          {formatPercent(getValue() as number)}
        </span>
      ),
    },
  ];
}

/** Collapse data to top N items + "Other" for clean pie charts */
function topN(data: DeviceRow[], n: number = 6): { name: string; value: number }[] {
  if (!data || data.length === 0) return [];
  const sorted = [...data].sort((a, b) => b.visitors - a.visitors);
  const top = sorted.slice(0, n);
  const rest = sorted.slice(n);
  const result = top.map((d) => ({ name: d.value || "(unknown)", value: d.visitors }));
  if (rest.length > 0) {
    const otherTotal = rest.reduce((s, d) => s + d.visitors, 0);
    result.push({ name: "Other", value: otherTotal });
  }
  return result;
}

function BarVisualization({ data }: { data: DeviceRow[] }) {
  const max = Math.max(...data.map((d) => d.visitors), 1);
  return (
    <div className="space-y-1.5">
      {data.map((item, i) => (
        <div key={item.value} className="flex items-center gap-2 text-sm">
          <div
            className="h-2.5 w-2.5 shrink-0 rounded-full"
            style={{ backgroundColor: CHART_COLORS[i % CHART_COLORS.length] }}
          />
          <span className="w-24 truncate text-xs">{item.value || "(unknown)"}</span>
          <div className="flex-1">
            <div
              className="h-5 rounded-sm bg-primary/15"
              style={{ width: `${(item.visitors / max) * 100}%` }}
            />
          </div>
          <span className="w-16 text-right text-xs tabular-nums text-muted-foreground">
            {item.visitors.toLocaleString()}
          </span>
          <span className="w-12 text-right text-xs tabular-nums text-muted-foreground">
            {formatPercent(item.percentage)}
          </span>
        </div>
      ))}
    </div>
  );
}

type ViewMode = "chart" | "list";

function DeviceCard({
  title,
  data,
  isLoading,
}: {
  title: string;
  data: DeviceRow[];
  isLoading: boolean;
}) {
  const [viewMode, setViewMode] = useState<ViewMode>("chart");
  const pieData = useMemo(() => topN(data, 6), [data]);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <div className="flex items-center gap-0.5 rounded-md border p-0.5">
          <button
            onClick={() => setViewMode("chart")}
            className={`rounded-sm p-1 transition-colors ${
              viewMode === "chart"
                ? "bg-muted text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
            title="Chart view"
          >
            <PieChartIcon className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => setViewMode("list")}
            className={`rounded-sm p-1 transition-colors ${
              viewMode === "list"
                ? "bg-muted text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
            title="List view"
          >
            <BarChart3 className="h-3.5 w-3.5" />
          </button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex h-[240px] items-center justify-center">
            <p className="text-sm text-muted-foreground">Loading...</p>
          </div>
        ) : viewMode === "chart" ? (
          <DonutChart
            data={pieData}
            height={240}
            outerRadius={80}
          />
        ) : (
          <BarVisualization data={data} />
        )}
      </CardContent>
    </Card>
  );
}

export function DevicesPage() {
  const { data, isLoading } = useSiteQuery<DevicesData>("devices", [
    "devices",
  ]);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-3">
        <DeviceCard
          title="Browsers"
          data={data?.browsers ?? []}
          isLoading={isLoading}
        />
        <DeviceCard
          title="Operating Systems"
          data={data?.os ?? []}
          isLoading={isLoading}
        />
        <DeviceCard
          title="Devices"
          data={data?.devices ?? []}
          isLoading={isLoading}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Screen Sizes</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <p className="text-sm text-muted-foreground">Loading...</p>
            ) : (
              <DataTable
                columns={deviceColumns("Screen")}
                data={data?.screens ?? []}
                emptyMessage="No screen data"
                compact
                showPagination={false}
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Languages</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <p className="text-sm text-muted-foreground">Loading...</p>
            ) : (
              <DataTable
                columns={deviceColumns("Language")}
                data={data?.languages ?? []}
                emptyMessage="No language data"
                compact
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
