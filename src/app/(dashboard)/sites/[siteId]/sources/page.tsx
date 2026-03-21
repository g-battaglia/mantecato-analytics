"use client";

import { useState, useMemo } from "react";
import { type ColumnDef } from "@tanstack/react-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable } from "@/components/data/DataTable";
import { BarChart } from "@/components/charts/BarChart";
import { useSiteQuery } from "@/hooks/use-site-query";
import { formatDuration, formatPercent } from "@/lib/format";

// --- Types ---

interface ReferrerRow {
  referrerDomain: string;
  visitors: number;
  pageviews: number;
  bounceRate: number;
  avgDuration: number;
}

interface ChannelRow {
  channel: string;
  visitors: number;
  pageviews: number;
  bounceRate: number;
  avgDuration: number;
}

interface UTMDetailRow {
  value: string;
  visitors: number;
  pageviews: number;
  bounceRate: number;
  avgDuration: number;
}

interface ClickIdRow {
  platform: string;
  visitors: number;
  pageviews: number;
  bounceRate: number;
  avgDuration: number;
}

interface HostnameRow {
  hostname: string;
  visitors: number;
  pageviews: number;
  bounceRate: number;
  avgDuration: number;
}

// --- Column definitions ---

const referrerColumns: ColumnDef<ReferrerRow>[] = [
  { accessorKey: "referrerDomain", header: "Source", enableSorting: false },
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
    accessorKey: "pageviews",
    header: () => <span className="flex justify-end">Pageviews</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toLocaleString()}
      </span>
    ),
  },
  {
    accessorKey: "bounceRate",
    header: () => <span className="flex justify-end">Bounce Rate</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {formatPercent(getValue() as number)}
      </span>
    ),
  },
  {
    accessorKey: "avgDuration",
    header: () => <span className="flex justify-end">Avg Duration</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {formatDuration(getValue() as number)}
      </span>
    ),
  },
];

const channelColumns: ColumnDef<ChannelRow>[] = [
  { accessorKey: "channel", header: "Channel", enableSorting: false },
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
    accessorKey: "pageviews",
    header: () => <span className="flex justify-end">Pageviews</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toLocaleString()}
      </span>
    ),
  },
  {
    accessorKey: "bounceRate",
    header: () => <span className="flex justify-end">Bounce Rate</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {formatPercent(getValue() as number)}
      </span>
    ),
  },
  {
    accessorKey: "avgDuration",
    header: () => <span className="flex justify-end">Avg Duration</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {formatDuration(getValue() as number)}
      </span>
    ),
  },
];

const clickIdColumns: ColumnDef<ClickIdRow>[] = [
  { accessorKey: "platform", header: "Platform", enableSorting: false },
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
    accessorKey: "pageviews",
    header: () => <span className="flex justify-end">Pageviews</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toLocaleString()}
      </span>
    ),
  },
  {
    accessorKey: "bounceRate",
    header: () => <span className="flex justify-end">Bounce Rate</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {formatPercent(getValue() as number)}
      </span>
    ),
  },
  {
    accessorKey: "avgDuration",
    header: () => <span className="flex justify-end">Avg Duration</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {formatDuration(getValue() as number)}
      </span>
    ),
  },
];

const hostnameColumns: ColumnDef<HostnameRow>[] = [
  {
    accessorKey: "hostname",
    header: "Hostname",
    enableSorting: false,
    cell: ({ getValue }) => (
      <span className="font-mono text-xs">{getValue() as string}</span>
    ),
  },
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
    accessorKey: "pageviews",
    header: () => <span className="flex justify-end">Pageviews</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toLocaleString()}
      </span>
    ),
  },
  {
    accessorKey: "bounceRate",
    header: () => <span className="flex justify-end">Bounce Rate</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {formatPercent(getValue() as number)}
      </span>
    ),
  },
  {
    accessorKey: "avgDuration",
    header: () => <span className="flex justify-end">Avg Duration</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {formatDuration(getValue() as number)}
      </span>
    ),
  },
];

function makeUtmColumns(dimensionLabel: string): ColumnDef<UTMDetailRow>[] {
  return [
    {
      accessorKey: "value",
      header: dimensionLabel,
      enableSorting: false,
      cell: ({ getValue }) => (
        <span className="font-mono text-xs">{getValue() as string}</span>
      ),
    },
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
      accessorKey: "pageviews",
      header: () => <span className="flex justify-end">Pageviews</span>,
      cell: ({ getValue }) => (
        <span className="flex justify-end tabular-nums">
          {(getValue() as number).toLocaleString()}
        </span>
      ),
    },
    {
      accessorKey: "bounceRate",
      header: () => <span className="flex justify-end">Bounce Rate</span>,
      cell: ({ getValue }) => (
        <span className="flex justify-end tabular-nums">
          {formatPercent(getValue() as number)}
        </span>
      ),
    },
    {
      accessorKey: "avgDuration",
      header: () => <span className="flex justify-end">Avg Duration</span>,
      cell: ({ getValue }) => (
        <span className="flex justify-end tabular-nums">
          {formatDuration(getValue() as number)}
        </span>
      ),
    },
  ];
}

// --- UTM Dimension Panel ---

const UTM_DIMENSIONS = [
  { key: "utm_source", label: "Source" },
  { key: "utm_medium", label: "Medium" },
  { key: "utm_campaign", label: "Campaign" },
  { key: "utm_content", label: "Content" },
  { key: "utm_term", label: "Term" },
] as const;

function UTMDimensionPanel({ dimension }: { dimension: string }) {
  const extraParams = useMemo(
    () => ({ view: "utm-detail", dimension }),
    [dimension]
  );
  const { data, isLoading } = useSiteQuery<UTMDetailRow[]>(
    "sources",
    ["sources-utm-detail", dimension],
    extraParams
  );

  const dimInfo = UTM_DIMENSIONS.find((d) => d.key === dimension);
  const columns = useMemo(
    () => makeUtmColumns(dimInfo?.label ?? "Value"),
    [dimInfo]
  );

  const chartData = (data ?? []).slice(0, 8).map((row) => ({
    name: row.value.length > 20 ? row.value.slice(0, 20) + "..." : row.value,
    visitors: row.visitors,
  }));

  return (
    <div className="space-y-4">
      {chartData.length > 0 && (
        <BarChart
          data={chartData}
          xKey="name"
          yKeys={["visitors"]}
          labels={{ visitors: "Visitors" }}
          height={200}
          horizontal
        />
      )}
      <DataTable
        columns={columns}
        data={data ?? []}
        loading={isLoading}
        searchColumn="value"
        searchPlaceholder={`Search ${dimInfo?.label.toLowerCase()}...`}
        emptyMessage={`No ${dimInfo?.label.toLowerCase()} data`}
        exportFilename={`utm-${dimension}`}
      />
    </div>
  );
}

// --- Main page ---

export default function SourcesPage() {
  const [tab, setTab] = useState("referrers");
  const [utmDim, setUtmDim] = useState("utm_source");

  const { data: referrers, isLoading: refLoading } =
    useSiteQuery<ReferrerRow[]>("sources", ["sources-referrers"], {
      view: "referrers",
    });

  const channelsParams = useMemo(() => ({ view: "channels" }), []);
  const { data: channels, isLoading: chLoading } =
    useSiteQuery<ChannelRow[]>("sources", ["sources-channels"], channelsParams);

  const clickIdParams = useMemo(() => ({ view: "click-ids" }), []);
  const { data: clickIds, isLoading: ciLoading } =
    useSiteQuery<ClickIdRow[]>("sources", ["sources-click-ids"], clickIdParams);

  const hostnameParams = useMemo(() => ({ view: "hostnames" }), []);
  const { data: hostnames, isLoading: hnLoading } =
    useSiteQuery<HostnameRow[]>("sources", ["sources-hostnames"], hostnameParams);

  // Chart data for channels
  const channelChartData = (channels ?? []).map((row) => ({
    name: row.channel,
    visitors: row.visitors,
  }));

  // Chart data for click IDs
  const clickIdChartData = (clickIds ?? []).map((row) => ({
    name: row.platform,
    visitors: row.visitors,
  }));

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">
            Traffic Sources
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              <TabsTrigger value="referrers">Referrers</TabsTrigger>
              <TabsTrigger value="channels">Channels</TabsTrigger>
              <TabsTrigger value="utm">UTM</TabsTrigger>
              <TabsTrigger value="click-ids">Click IDs</TabsTrigger>
              <TabsTrigger value="hostnames">Hostnames</TabsTrigger>
            </TabsList>

            <TabsContent value="referrers" className="mt-4">
              <DataTable
                columns={referrerColumns}
                data={referrers ?? []}
                loading={refLoading}
                searchColumn="referrerDomain"
                searchPlaceholder="Search sources..."
                emptyMessage="No referrer data"
                exportFilename="referrers"
              />
            </TabsContent>

            <TabsContent value="channels" className="mt-4 space-y-4">
              {channelChartData.length > 0 && (
                <BarChart
                  data={channelChartData}
                  xKey="name"
                  yKeys={["visitors"]}
                  labels={{ visitors: "Visitors" }}
                  height={220}
                  horizontal
                />
              )}
              <DataTable
                columns={channelColumns}
                data={channels ?? []}
                loading={chLoading}
                emptyMessage="No channel data"
                exportFilename="channels"
              />
            </TabsContent>

            <TabsContent value="utm" className="mt-4 space-y-4">
              {/* Sub-tabs for UTM dimensions */}
              <Tabs value={utmDim} onValueChange={setUtmDim}>
                <TabsList>
                  {UTM_DIMENSIONS.map((d) => (
                    <TabsTrigger key={d.key} value={d.key}>
                      {d.label}
                    </TabsTrigger>
                  ))}
                </TabsList>
                {UTM_DIMENSIONS.map((d) => (
                  <TabsContent key={d.key} value={d.key} className="mt-4">
                    <UTMDimensionPanel dimension={d.key} />
                  </TabsContent>
                ))}
              </Tabs>
            </TabsContent>

            <TabsContent value="click-ids" className="mt-4 space-y-4">
              {clickIdChartData.length > 0 && (
                <BarChart
                  data={clickIdChartData}
                  xKey="name"
                  yKeys={["visitors"]}
                  labels={{ visitors: "Visitors" }}
                  height={220}
                  horizontal
                />
              )}
              <DataTable
                columns={clickIdColumns}
                data={clickIds ?? []}
                loading={ciLoading}
                emptyMessage="No paid click ID data — visits with gclid, fbclid, msclkid, etc. will appear here"
                exportFilename="click-ids"
              />
            </TabsContent>

            <TabsContent value="hostnames" className="mt-4">
              <DataTable
                columns={hostnameColumns}
                data={hostnames ?? []}
                loading={hnLoading}
                searchColumn="hostname"
                searchPlaceholder="Search hostnames..."
                emptyMessage="No hostname data"
                exportFilename="hostnames"
              />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
