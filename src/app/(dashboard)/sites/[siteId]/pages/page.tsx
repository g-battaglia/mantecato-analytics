"use client";

import { useState, useMemo } from "react";
import { type ColumnDef } from "@tanstack/react-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/data/DataTable";
import { MetricCard } from "@/components/data/MetricCard";
import { BarChart } from "@/components/charts/BarChart";
import { AreaChart } from "@/components/charts/AreaChart";
import { useSiteQuery, useDateParams } from "@/hooks/use-site-query";
import { usePreferencesStore } from "@/stores/preferences";
import { formatDuration, formatPercent } from "@/lib/format";
import { ArrowLeft, ArrowRight } from "lucide-react";

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

interface PageDetail {
  timeseries: { time: string; views: number; visitors: number }[];
  referrers: { referrerDomain: string; visitors: number; views: number }[];
  nextPages: { urlPath: string; count: number; percentage: number }[];
  timeDistribution: { bucket: string; count: number }[];
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
  const [selectedPage, setSelectedPage] = useState<PageRow | null>(null);
  const pageMode = usePreferencesStore((s) => s.pageMode);
  const { data, isLoading } = useSiteQuery<PageRow[]>("pages", ["pages"], {
    mode: pageMode,
  });

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

  // If a page is selected, show its detail view
  if (selectedPage) {
    return (
      <PageDetailView
        page={selectedPage}
        onBack={() => setSelectedPage(null)}
      />
    );
  }

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
                onRowClick={(row) => setSelectedPage(row)}
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
                onRowClick={(row) => setSelectedPage(row)}
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
                onRowClick={(row) => setSelectedPage(row)}
              />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}

// --- Page Detail View ---

function PageDetailView({
  page,
  onBack,
}: {
  page: PageRow;
  onBack: () => void;
}) {
  const { data, isLoading } = useSiteQuery<PageDetail>("pages", [
    "page-detail",
    page.urlPath,
  ], {
    page: page.urlPath,
  });

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="sm"
          className="gap-1.5"
          onClick={onBack}
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back
        </Button>
        <div className="min-w-0 flex-1">
          <h2 className="truncate font-mono text-sm font-medium">
            {page.urlPath}
          </h2>
          {page.pageTitle && (
            <p className="truncate text-xs text-muted-foreground">
              {page.pageTitle}
            </p>
          )}
        </div>
      </div>

      {/* Metrics */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
        <MetricCard
          label="Views"
          value={page.views}
          tooltip="Total views for this page"
        />
        <MetricCard
          label="Visitors"
          value={page.visitors}
          tooltip="Unique visitors for this page"
        />
        <MetricCard
          label="Avg Time"
          value={page.avgTimeOnPage}
          format="duration"
          tooltip="Average time spent on this page"
        />
        <MetricCard
          label="Bounce Rate"
          value={page.bounceRate}
          format="percent"
          tooltip="Percentage of single-page visits landing on this page"
        />
        <MetricCard
          label="Entries"
          value={page.entries}
          tooltip="Number of visits that started on this page"
        />
        <MetricCard
          label="Exits"
          value={page.exits}
          tooltip="Number of visits that ended on this page"
        />
      </div>

      {/* Time series */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Views Over Time</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex h-[250px] items-center justify-center text-sm text-muted-foreground">
              Loading...
            </div>
          ) : data?.timeseries && data.timeseries.length > 0 ? (
            <AreaChart
              data={data.timeseries}
              xKey="time"
              yKeys={["views", "visitors"]}
              labels={{ views: "Views", visitors: "Visitors" }}
              height={250}
            />
          ) : (
            <div className="flex h-[250px] items-center justify-center text-sm text-muted-foreground">
              No data
            </div>
          )}
        </CardContent>
      </Card>

      {/* Bottom panels */}
      <div className="grid gap-4 lg:grid-cols-3">
        {/* Time on page distribution */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Time on Page Distribution
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex h-[200px] items-center justify-center text-sm text-muted-foreground">
                Loading...
              </div>
            ) : data?.timeDistribution && data.timeDistribution.length > 0 ? (
              <BarChart
                data={data.timeDistribution}
                xKey="bucket"
                yKeys={["count"]}
                labels={{ count: "Views" }}
                height={200}
              />
            ) : (
              <div className="flex h-[200px] items-center justify-center text-sm text-muted-foreground">
                No data
              </div>
            )}
          </CardContent>
        </Card>

        {/* Referrers to this page */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Top Referrers
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex h-[200px] items-center justify-center text-sm text-muted-foreground">
                Loading...
              </div>
            ) : data?.referrers && data.referrers.length > 0 ? (
              <div className="space-y-1.5">
                {data.referrers.map((r, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between gap-2 text-xs"
                  >
                    <span className="truncate">{r.referrerDomain}</span>
                    <span className="shrink-0 tabular-nums font-medium">
                      {r.visitors.toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex h-[200px] items-center justify-center text-sm text-muted-foreground">
                No referrer data
              </div>
            )}
          </CardContent>
        </Card>

        {/* Where visitors go next */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Next Pages
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex h-[200px] items-center justify-center text-sm text-muted-foreground">
                Loading...
              </div>
            ) : data?.nextPages && data.nextPages.length > 0 ? (
              <div className="space-y-1.5">
                {data.nextPages.map((np, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between gap-2 text-xs"
                  >
                    <span className="flex items-center gap-1 truncate">
                      <ArrowRight className="h-3 w-3 shrink-0 text-muted-foreground" />
                      <span className="truncate font-mono">{np.urlPath}</span>
                    </span>
                    <span className="shrink-0 tabular-nums text-muted-foreground">
                      {np.percentage.toFixed(1)}%
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex h-[200px] items-center justify-center text-sm text-muted-foreground">
                No next-page data
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
