"use client";

import { useState, useMemo } from "react";
import { type ColumnDef } from "@tanstack/react-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable } from "@/components/data/DataTable";
import { MetricCard } from "@/components/data/MetricCard";
import { BarChart } from "@/components/charts/BarChart";
import { useSiteQuery } from "@/hooks/use-site-query";
import { formatDuration, formatPercent } from "@/lib/format";

interface PageRow {
  urlPath: string;
  pageTitle: string | null;
  views: number;
  visitors: number;
  avgTimeOnPage: number | null;
  medianTimeOnPage: number | null;
  entries: number;
  exits: number;
  bounceRate: number;
}

// --- Column definitions ---

const allPagesColumns: ColumnDef<PageRow>[] = [
  {
    accessorKey: "urlPath",
    header: "Page",
    cell: ({ row }) => (
      <div className="max-w-[300px]">
        <span className="block truncate font-mono text-xs">
          {row.original.urlPath}
        </span>
        {row.original.pageTitle && (
          <span className="block truncate text-xs text-muted-foreground">
            {row.original.pageTitle}
          </span>
        )}
      </div>
    ),
    enableSorting: false,
  },
  {
    accessorKey: "views",
    header: () => <span className="flex justify-end">Views</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toLocaleString()}
      </span>
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
    accessorKey: "avgTimeOnPage",
    header: () => <span className="flex justify-end">Avg Time</span>,
    cell: ({ getValue }) => {
      const v = getValue() as number | null;
      return (
        <span className="flex justify-end tabular-nums">
          {v != null ? formatDuration(v) : "--"}
        </span>
      );
    },
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
    accessorKey: "entries",
    header: () => <span className="flex justify-end">Entries</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toLocaleString()}
      </span>
    ),
  },
  {
    accessorKey: "exits",
    header: () => <span className="flex justify-end">Exits</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toLocaleString()}
      </span>
    ),
  },
];

const entryColumns: ColumnDef<PageRow>[] = [
  {
    accessorKey: "urlPath",
    header: "Entry Page",
    cell: ({ row }) => (
      <div className="max-w-[300px]">
        <span className="block truncate font-mono text-xs">
          {row.original.urlPath}
        </span>
        {row.original.pageTitle && (
          <span className="block truncate text-xs text-muted-foreground">
            {row.original.pageTitle}
          </span>
        )}
      </div>
    ),
    enableSorting: false,
  },
  {
    accessorKey: "entries",
    header: () => <span className="flex justify-end">Entries</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toLocaleString()}
      </span>
    ),
  },
  {
    id: "entryPct",
    header: () => <span className="flex justify-end">% of Entries</span>,
    cell: () => null, // computed dynamically below
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
    accessorKey: "avgTimeOnPage",
    header: () => <span className="flex justify-end">Avg Time</span>,
    cell: ({ getValue }) => {
      const v = getValue() as number | null;
      return (
        <span className="flex justify-end tabular-nums">
          {v != null ? formatDuration(v) : "--"}
        </span>
      );
    },
  },
];

const exitColumns: ColumnDef<PageRow>[] = [
  {
    accessorKey: "urlPath",
    header: "Exit Page",
    cell: ({ row }) => (
      <div className="max-w-[300px]">
        <span className="block truncate font-mono text-xs">
          {row.original.urlPath}
        </span>
        {row.original.pageTitle && (
          <span className="block truncate text-xs text-muted-foreground">
            {row.original.pageTitle}
          </span>
        )}
      </div>
    ),
    enableSorting: false,
  },
  {
    accessorKey: "exits",
    header: () => <span className="flex justify-end">Exits</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toLocaleString()}
      </span>
    ),
  },
  {
    id: "exitPct",
    header: () => <span className="flex justify-end">% of Exits</span>,
    cell: () => null, // computed dynamically below
  },
  {
    accessorKey: "views",
    header: () => <span className="flex justify-end">Views</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toLocaleString()}
      </span>
    ),
  },
  {
    id: "exitRate",
    header: () => <span className="flex justify-end">Exit Rate</span>,
    cell: () => null, // computed dynamically below
  },
];

export default function PagesPage() {
  const [tab, setTab] = useState("all");
  const { data, isLoading } = useSiteQuery<PageRow[]>("pages", ["pages"]);

  const pages = data ?? [];

  // Derived data for entry/exit views
  const totalEntries = useMemo(
    () => pages.reduce((sum, p) => sum + p.entries, 0),
    [pages]
  );
  const totalExits = useMemo(
    () => pages.reduce((sum, p) => sum + p.exits, 0),
    [pages]
  );
  const totalViews = useMemo(
    () => pages.reduce((sum, p) => sum + p.views, 0),
    [pages]
  );

  // Entry pages sorted by entries desc
  const entryPages = useMemo(
    () => [...pages].filter((p) => p.entries > 0).sort((a, b) => b.entries - a.entries),
    [pages]
  );

  // Exit pages sorted by exits desc
  const exitPages = useMemo(
    () => [...pages].filter((p) => p.exits > 0).sort((a, b) => b.exits - a.exits),
    [pages]
  );

  // Dynamic columns with computed percentages
  const entryColumnsWithPct: ColumnDef<PageRow>[] = useMemo(() => {
    return entryColumns.map((col) => {
      if ("id" in col && col.id === "entryPct") {
        return {
          ...col,
          cell: ({ row }: { row: { original: PageRow } }) => (
            <span className="flex justify-end tabular-nums">
              {totalEntries > 0
                ? formatPercent((row.original.entries / totalEntries) * 100)
                : "--"}
            </span>
          ),
        };
      }
      return col;
    });
  }, [totalEntries]);

  const exitColumnsWithPct: ColumnDef<PageRow>[] = useMemo(() => {
    return exitColumns.map((col) => {
      if ("id" in col && col.id === "exitPct") {
        return {
          ...col,
          cell: ({ row }: { row: { original: PageRow } }) => (
            <span className="flex justify-end tabular-nums">
              {totalExits > 0
                ? formatPercent((row.original.exits / totalExits) * 100)
                : "--"}
            </span>
          ),
        };
      }
      if ("id" in col && col.id === "exitRate") {
        return {
          ...col,
          cell: ({ row }: { row: { original: PageRow } }) => (
            <span className="flex justify-end tabular-nums">
              {row.original.views > 0
                ? formatPercent((row.original.exits / row.original.views) * 100)
                : "--"}
            </span>
          ),
        };
      }
      return col;
    });
  }, [totalExits]);

  // Chart data for top 8 entries / exits
  const entryChartData = entryPages.slice(0, 8).map((p) => ({
    name: p.urlPath.length > 30 ? p.urlPath.slice(0, 30) + "..." : p.urlPath,
    entries: p.entries,
  }));

  const exitChartData = exitPages.slice(0, 8).map((p) => ({
    name: p.urlPath.length > 30 ? p.urlPath.slice(0, 30) + "..." : p.urlPath,
    exits: p.exits,
  }));

  return (
    <div className="space-y-4">
      {/* Summary metrics */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Total Pages"
          value={pages.length}
          loading={isLoading}
          tooltip="Number of unique pages visited in the selected period"
        />
        <MetricCard
          label="Total Views"
          value={totalViews}
          loading={isLoading}
          tooltip="Sum of all page views across all pages"
        />
        <MetricCard
          label="Total Entries"
          value={totalEntries}
          loading={isLoading}
          tooltip="Total number of visits that started (first pageview) on any page"
        />
        <MetricCard
          label="Total Exits"
          value={totalExits}
          loading={isLoading}
          tooltip="Total number of visits where the last pageview was on any page"
        />
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Pages</CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              <TabsTrigger value="all">All Pages</TabsTrigger>
              <TabsTrigger value="entry">Entry Pages</TabsTrigger>
              <TabsTrigger value="exit">Exit Pages</TabsTrigger>
            </TabsList>

            <TabsContent value="all" className="mt-4">
              <DataTable
                columns={allPagesColumns}
                data={pages}
                loading={isLoading}
                searchColumn="urlPath"
                searchPlaceholder="Search pages..."
                emptyMessage="No page data for this period"
                exportFilename="pages"
              />
            </TabsContent>

            <TabsContent value="entry" className="mt-4 space-y-4">
              {entryChartData.length > 0 && (
                <BarChart
                  data={entryChartData}
                  xKey="name"
                  yKeys={["entries"]}
                  labels={{ entries: "Entries" }}
                  height={220}
                  horizontal
                />
              )}
              <DataTable
                columns={entryColumnsWithPct}
                data={entryPages}
                loading={isLoading}
                searchColumn="urlPath"
                searchPlaceholder="Search entry pages..."
                emptyMessage="No entry page data"
                exportFilename="entry-pages"
              />
            </TabsContent>

            <TabsContent value="exit" className="mt-4 space-y-4">
              {exitChartData.length > 0 && (
                <BarChart
                  data={exitChartData}
                  xKey="name"
                  yKeys={["exits"]}
                  labels={{ exits: "Exits" }}
                  height={220}
                  horizontal
                />
              )}
              <DataTable
                columns={exitColumnsWithPct}
                data={exitPages}
                loading={isLoading}
                searchColumn="urlPath"
                searchPlaceholder="Search exit pages..."
                emptyMessage="No exit page data"
                exportFilename="exit-pages"
              />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
