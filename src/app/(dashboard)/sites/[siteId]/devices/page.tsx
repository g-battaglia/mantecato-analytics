"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable, type Column } from "@/components/data/DataTable";
import { useSiteQuery } from "@/hooks/use-site-query";
import { formatPercent } from "@/lib/format";

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

function deviceColumns(label: string): Column<DeviceRow>[] {
  return [
    { key: "value", label },
    {
      key: "visitors",
      label: "Visitors",
      align: "right",
      render: (row) => row.visitors.toLocaleString(),
    },
    {
      key: "percentage",
      label: "%",
      align: "right",
      render: (row) => formatPercent(row.percentage),
    },
  ];
}

function BarVisualization({ data }: { data: DeviceRow[] }) {
  const max = Math.max(...data.map((d) => d.visitors), 1);
  return (
    <div className="space-y-1.5">
      {data.map((item) => (
        <div key={item.value} className="flex items-center gap-2 text-sm">
          <span className="w-24 truncate text-xs">{item.value}</span>
          <div className="flex-1">
            <div
              className="h-5 rounded-sm bg-primary/20"
              style={{ width: `${(item.visitors / max) * 100}%` }}
            />
          </div>
          <span className="w-12 text-right text-xs tabular-nums text-muted-foreground">
            {formatPercent(item.percentage)}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function DevicesPage() {
  const { data, isLoading } = useSiteQuery<DevicesData>("devices", [
    "devices",
  ]);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Browsers</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <p className="text-sm text-muted-foreground">Loading...</p>
            ) : (
              <BarVisualization data={data?.browsers ?? []} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Operating Systems
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <p className="text-sm text-muted-foreground">Loading...</p>
            ) : (
              <BarVisualization data={data?.os ?? []} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Devices</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <p className="text-sm text-muted-foreground">Loading...</p>
            ) : (
              <BarVisualization data={data?.devices ?? []} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Screen Sizes
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <p className="text-sm text-muted-foreground">Loading...</p>
            ) : (
              <DataTable
                columns={deviceColumns("Screen")}
                data={data?.screens ?? []}
                rowKey={(row) => row.value}
                emptyMessage="No screen data"
              />
            )}
          </CardContent>
        </Card>
      </div>

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
              rowKey={(row) => row.value}
              emptyMessage="No language data"
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
