import { useMemo, useState } from "react";
import { useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { useDateParams } from "@/hooks/use-site-query";
import { MetricCard } from "@/components/data/MetricCard";
import { BarChart } from "@/components/charts/BarChart";
import {
  SankeyChart,
  buildSankeyFromJourneys,
} from "@/components/charts/SankeyChart";
import { DataTable, numericColumn, percentColumn } from "@/components/data/DataTable";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDuration, formatPercent, formatNumber } from "@/lib/format";
import type { ColumnDef } from "@tanstack/react-table";
import { apiFetch } from "@/lib/api";
import { ArrowRight } from "lucide-react";

interface EngagementData {
  distribution: Array<{
    bucket: string;
    bucketOrder: number;
    visits: number;
    percentage: number;
  }>;
  percentiles: {
    p50: number;
    p75: number;
    p90: number;
    p95: number;
    p99: number;
    avg: number;
    median: number;
    min: number;
    max: number;
    totalVisits: number;
  };
  durationByPage: Array<{
    urlPath: string;
    views: number;
    avgDuration: number;
    medianDuration: number;
    p90Duration: number;
  }>;
  bounceByPage: Array<{
    urlPath: string;
    totalVisits: number;
    bounces: number;
    bounceRate: number;
  }>;
  bounceBySource: Array<{
    referrerDomain: string;
    totalVisits: number;
    bounces: number;
    bounceRate: number;
  }>;
}

interface BucketData {
  sessions: Array<{
    visitId: string;
    sessionId: string;
    country: string;
    city: string;
    browser: string;
    os: string;
    device: string;
    landingPage: string;
    pagesViewed: number;
    durationSecs: number;
    startedAt: string;
  }>;
  total: number;
  countries: Array<{
    country: string;
    visits: number;
  }>;
  cities: Array<{
    country: string;
    city: string;
    visits: number;
  }>;
  pages: Array<{
    urlPath: string;
    views: number;
    visits: number;
  }>;
  entryPages: Array<{
    urlPath: string;
    visits: number;
    percentage: number;
  }>;
  journeys: Array<{
    path: string[];
    count: number;
    percentage: number;
  }>;
  sources: Array<{
    referrerDomain: string;
    visits: number;
  }>;
  devices: Array<{
    browser: string;
    device: string;
    os: string;
    visits: number;
  }>;
}

function formatBucketShare(visits: number, total: number): string {
  if (total <= 0) return "--";
  return formatPercent((visits / total) * 100);
}

function formatBucketStartedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function useEngagementData(siteId: string) {
  const { params, queryKeyParts } = useDateParams();
  return useQuery<EngagementData>({
    queryKey: ["engagement", siteId, ...queryKeyParts],
    queryFn: async () => {
      const res = await apiFetch(`/api/sites/${siteId}/engagement?${params}`);
      if (!res.ok) throw new Error("Failed to fetch engagement data");
      return res.json();
    },
  });
}

const durationByPageColumns: ColumnDef<EngagementData["durationByPage"][0]>[] = [
  { accessorKey: "urlPath", header: "Page", cell: ({ getValue }) => (
    <span className="font-mono text-xs truncate max-w-[300px] block">{getValue() as string}</span>
  )},
  numericColumn("views", "Views"),
  {
    accessorKey: "avgDuration",
    header: () => <span className="flex justify-end">Avg Duration</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">{formatDuration(getValue() as number)}</span>
    ),
  },
  {
    accessorKey: "medianDuration",
    header: () => <span className="flex justify-end">Median</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">{formatDuration(getValue() as number)}</span>
    ),
  },
  {
    accessorKey: "p90Duration",
    header: () => <span className="flex justify-end">P90</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">{formatDuration(getValue() as number)}</span>
    ),
  },
];

const bounceByPageColumns: ColumnDef<EngagementData["bounceByPage"][0]>[] = [
  { accessorKey: "urlPath", header: "Entry Page", cell: ({ getValue }) => (
    <span className="font-mono text-xs truncate max-w-[300px] block">{getValue() as string}</span>
  )},
  numericColumn("totalVisits", "Visits"),
  numericColumn("bounces", "Bounces"),
  percentColumn("bounceRate", "Bounce Rate"),
];

const bounceBySourceColumns: ColumnDef<EngagementData["bounceBySource"][0]>[] = [
  { accessorKey: "referrerDomain", header: "Source" },
  numericColumn("totalVisits", "Visits"),
  numericColumn("bounces", "Bounces"),
  percentColumn("bounceRate", "Bounce Rate"),
];

export function EngagementPage() {
  const params = useParams();
  const siteId = params.siteId as string;
  const { data, isLoading } = useEngagementData(siteId);
  const [selectedBucket, setSelectedBucket] = useState<string | null>(null);
  const [selectedEntryPage, setSelectedEntryPage] = useState<string | null>(null);

  const p = data?.percentiles;

  const { params: dateParams } = useDateParams();
  const { data: bucketData, isLoading: bucketLoading } = useQuery<BucketData>({
    queryKey: ["bucket-sessions", siteId, selectedBucket, dateParams.toString()],
    enabled: !!selectedBucket,
    queryFn: async () => {
      const p = new URLSearchParams(dateParams);
      p.set("bucket", selectedBucket!);
      const res = await apiFetch(`/api/sites/${siteId}/engagement/bucket-sessions?${p}`);
      if (!res.ok) throw new Error("Failed to fetch bucket sessions");
      return res.json() as Promise<BucketData>;
    },
  });

  const {
    data: filteredMovementData,
    isLoading: filteredMovementLoading,
  } = useQuery<BucketData>({
    queryKey: [
      "bucket-sessions",
      siteId,
      selectedBucket,
      selectedEntryPage,
      dateParams.toString(),
    ],
    enabled: !!selectedBucket && !!selectedEntryPage,
    queryFn: async () => {
      const p = new URLSearchParams(dateParams);
      p.set("bucket", selectedBucket!);
      p.set("entryPage", selectedEntryPage!);
      const res = await apiFetch(`/api/sites/${siteId}/engagement/bucket-sessions?${p}`);
      if (!res.ok) throw new Error("Failed to fetch filtered movement data");
      return res.json() as Promise<BucketData>;
    },
  });

  const activeMovementData = selectedEntryPage
    ? (filteredMovementData ?? null)
    : bucketData;

  const bucketJourneyFlow = useMemo(() => {
    if (!activeMovementData?.journeys?.length) return null;
    return buildSankeyFromJourneys(activeMovementData.journeys, 6);
  }, [activeMovementData]);

  return (
    <div className="space-y-4">
      {/* Duration percentile cards */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        <MetricCard
          label="Median Duration"
          value={p?.median ?? null}
          format="duration"
          tooltip="50th percentile — half of all visits are shorter than this"
          loading={isLoading}
        />
        <MetricCard
          label="Avg Duration"
          value={p?.avg ?? null}
          format="duration"
          tooltip="Mean visit duration. Skewed by long sessions — compare with median for a clearer picture"
          loading={isLoading}
        />
        <MetricCard
          label="P75 Duration"
          value={p?.p75 ?? null}
          format="duration"
          tooltip="75th percentile — 75% of visits are shorter than this"
          loading={isLoading}
        />
        <MetricCard
          label="P90 Duration"
          value={p?.p90 ?? null}
          format="duration"
          tooltip="90th percentile — only 10% of visits last longer than this"
          loading={isLoading}
        />
        <MetricCard
          label="P99 Duration"
          value={p?.p99 ?? null}
          format="duration"
          tooltip="99th percentile — the longest 1% of visits exceed this duration"
          loading={isLoading}
        />
      </div>

      {/* Duration distribution histogram */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">
            Visit Duration Distribution
          </CardTitle>
          <CardDescription className="text-xs">
            How long visitors stay — grouped into time buckets. Excludes single-page bounces from percentile calculations.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-[300px] w-full" />
          ) : data?.distribution ? (
            <BarChart
              data={data.distribution.map((d) => ({
                name: d.bucket,
                visits: d.visits,
              }))}
              xKey="name"
              yKeys={["visits"]}
              labels={{ visits: "Visits" }}
              height={300}
              onBarClick={(payload) => {
                setSelectedEntryPage(null);
                setSelectedBucket(payload.name as string);
              }}
            />
          ) : null}
        </CardContent>
      </Card>

      {/* Duration by page */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">
            Time on Page
          </CardTitle>
          <CardDescription className="text-xs">
            How long visitors spend on each page before navigating away. Measured via the gap between consecutive pageviews in a visit.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DataTable
            columns={durationByPageColumns}
            data={data?.durationByPage ?? []}
            loading={isLoading}
            searchColumn="urlPath"
            searchPlaceholder="Filter pages..."
            exportFilename="time-on-page"
            compact
          />
        </CardContent>
      </Card>

      {/* Bounce rate tabs */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">
            Bounce Rate Breakdown
          </CardTitle>
          <CardDescription className="text-xs">
            Which entry pages and traffic sources have the highest bounce rates.
            A bounce is a visit with only one pageview.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="pages">
            <TabsList className="mb-3">
              <TabsTrigger value="pages">By Entry Page</TabsTrigger>
              <TabsTrigger value="sources">By Source</TabsTrigger>
            </TabsList>
            <TabsContent value="pages">
              <DataTable
                columns={bounceByPageColumns}
                data={data?.bounceByPage ?? []}
                loading={isLoading}
                searchColumn="urlPath"
                searchPlaceholder="Filter pages..."
                exportFilename="bounce-rate-by-page"
                compact
              />
            </TabsContent>
            <TabsContent value="sources">
              <DataTable
                columns={bounceBySourceColumns}
                data={data?.bounceBySource ?? []}
                loading={isLoading}
                searchColumn="referrerDomain"
                searchPlaceholder="Filter sources..."
                exportFilename="bounce-rate-by-source"
                compact
              />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      <Dialog
        open={!!selectedBucket}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedBucket(null);
            setSelectedEntryPage(null);
          }
        }}
      >
        <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-4xl">
          <DialogHeader>
            <DialogTitle>Visits: {selectedBucket}</DialogTitle>
            <DialogDescription>
              {bucketData
                ? `${formatNumber(bucketData.total, false)} visits in this duration range`
                : "Loading..."}
            </DialogDescription>
          </DialogHeader>
          {bucketLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : bucketData ? (
            <Tabs defaultValue="sessions" className="space-y-4">
              <TabsList className="grid h-auto w-full grid-cols-2 gap-1 sm:grid-cols-5">
                <TabsTrigger value="sessions">Sessions</TabsTrigger>
                <TabsTrigger value="geo">Geography</TabsTrigger>
                <TabsTrigger value="movement">Movement</TabsTrigger>
                <TabsTrigger value="pages">Pages</TabsTrigger>
                <TabsTrigger value="sources">Sources</TabsTrigger>
              </TabsList>

              <TabsContent value="sessions" className="space-y-0">
                {bucketData.sessions.length ? (
                  <div className="space-y-0">
                    <div className="mb-1 grid grid-cols-[110px_1fr_1fr_90px_56px_80px] gap-2 border-b pb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                      <span>Started</span>
                      <span>Location</span>
                      <span>Entry Page</span>
                      <span className="text-right">Browser</span>
                      <span className="text-right">Pages</span>
                      <span className="text-right">Duration</span>
                    </div>
                    {bucketData.sessions.map((session) => (
                      <div
                        key={session.visitId}
                        className="grid grid-cols-[110px_1fr_1fr_90px_56px_80px] items-center gap-2 py-1.5 text-sm"
                      >
                        <span className="text-xs text-muted-foreground">
                          {formatBucketStartedAt(session.startedAt)}
                        </span>
                        <span className="truncate text-xs">
                          {session.city && session.city !== "(not set)"
                            ? `${session.city}, `
                            : ""}
                          {session.country}
                        </span>
                        <span className="truncate font-mono text-xs">
                          {session.landingPage}
                        </span>
                        <span className="truncate text-right text-xs text-muted-foreground">
                          {session.browser}
                        </span>
                        <span className="text-right font-medium tabular-nums">
                          {session.pagesViewed}
                        </span>
                        <span className="text-right tabular-nums text-muted-foreground">
                          {formatDuration(session.durationSecs)}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="py-4 text-center text-xs text-muted-foreground">
                    No visits found
                  </p>
                )}
              </TabsContent>

              <TabsContent value="geo" className="grid gap-4 lg:grid-cols-2">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium">Countries</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-0">
                    {bucketData.countries.length ? (
                      <>
                        <div className="mb-1 grid grid-cols-[1fr_72px_72px] gap-2 border-b pb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                          <span>Country</span>
                          <span className="text-right">Visits</span>
                          <span className="text-right">Share</span>
                        </div>
                        {bucketData.countries.map((row) => (
                          <div
                            key={row.country}
                            className="grid grid-cols-[1fr_72px_72px] gap-2 py-1.5 text-xs"
                          >
                            <span className="truncate">{row.country}</span>
                            <span className="text-right tabular-nums">
                              {formatNumber(row.visits, false)}
                            </span>
                            <span className="text-right tabular-nums text-muted-foreground">
                              {formatBucketShare(row.visits, bucketData.total)}
                            </span>
                          </div>
                        ))}
                      </>
                    ) : (
                      <p className="py-4 text-center text-xs text-muted-foreground">
                        No geography data
                      </p>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium">Cities</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-0">
                    {bucketData.cities.length ? (
                      <>
                        <div className="mb-1 grid grid-cols-[1fr_72px_72px] gap-2 border-b pb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                          <span>City</span>
                          <span className="text-right">Visits</span>
                          <span className="text-right">Share</span>
                        </div>
                        {bucketData.cities.map((row) => (
                          <div
                            key={`${row.country}-${row.city}`}
                            className="grid grid-cols-[1fr_72px_72px] gap-2 py-1.5 text-xs"
                          >
                            <span className="truncate">{row.city}, {row.country}</span>
                            <span className="text-right tabular-nums">
                              {formatNumber(row.visits, false)}
                            </span>
                            <span className="text-right tabular-nums text-muted-foreground">
                              {formatBucketShare(row.visits, bucketData.total)}
                            </span>
                          </div>
                        ))}
                      </>
                    ) : (
                      <p className="py-4 text-center text-xs text-muted-foreground">
                        No city data
                      </p>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="movement" className="space-y-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium">Visit Flow</CardTitle>
                    <CardDescription className="text-xs">
                      {selectedEntryPage
                        ? `Showing only visits in ${selectedBucket} that start on ${selectedEntryPage}`
                        : "Select an entry page to isolate how that subset of visitors moves through the site"}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {filteredMovementLoading ? (
                      <Skeleton className="h-[320px] w-full" />
                    ) : bucketJourneyFlow ? (
                      <SankeyChart data={bucketJourneyFlow} height={320} />
                    ) : (
                      <div className="flex h-[320px] items-center justify-center text-sm text-muted-foreground">
                        {selectedEntryPage
                          ? "Not enough movement data for this entry page in the selected duration range"
                          : "Not enough movement data in this duration range"}
                      </div>
                    )}
                  </CardContent>
                </Card>

                <div className="grid gap-4 lg:grid-cols-2">
                  <Card>
                    <CardHeader className="pb-2">
                      <div className="flex items-center justify-between gap-2">
                        <CardTitle className="text-sm font-medium">Entry Pages</CardTitle>
                        {selectedEntryPage ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 text-xs"
                            onClick={() => setSelectedEntryPage(null)}
                          >
                            Clear filter
                          </Button>
                        ) : null}
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-0">
                      {bucketData.entryPages.length ? (
                        <>
                          <div className="mb-1 grid grid-cols-[1fr_72px_72px] gap-2 border-b pb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                            <span>First Page</span>
                            <span className="text-right">Visits</span>
                            <span className="text-right">Share</span>
                          </div>
                          {bucketData.entryPages.map((row) => (
                            <button
                              key={row.urlPath}
                              type="button"
                              onClick={() => setSelectedEntryPage(row.urlPath)}
                              className={`grid w-full grid-cols-[1fr_72px_72px] gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent ${
                                selectedEntryPage === row.urlPath ? "bg-accent" : ""
                              }`}
                            >
                              <span className="truncate font-mono">{row.urlPath}</span>
                              <span className="text-right tabular-nums">
                                {formatNumber(row.visits, false)}
                              </span>
                              <span className="text-right tabular-nums text-muted-foreground">
                                {formatPercent(row.percentage)}
                              </span>
                            </button>
                          ))}
                        </>
                      ) : (
                        <p className="py-4 text-center text-xs text-muted-foreground">
                          No entry-page data
                        </p>
                      )}
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium">Common Paths</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {filteredMovementLoading ? (
                        <div className="space-y-2">
                          <Skeleton className="h-16 w-full" />
                          <Skeleton className="h-16 w-full" />
                        </div>
                      ) : activeMovementData?.journeys.length ? (
                        activeMovementData.journeys.map((journey, index) => (
                          <div
                            key={`${journey.path.join("->")}-${index}`}
                            className="space-y-1 rounded-md border border-border/60 p-2"
                          >
                            <div className="flex flex-wrap items-center gap-1">
                              {journey.path.map((page, pageIndex) => (
                                <span key={`${page}-${pageIndex}`} className="flex items-center gap-1">
                                  {pageIndex > 0 && (
                                    <ArrowRight className="h-3 w-3 shrink-0 text-muted-foreground" />
                                  )}
                                  <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">
                                    {page}
                                  </span>
                                </span>
                              ))}
                            </div>
                            <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                              <span>{formatNumber(journey.count, false)} visits</span>
                              <span>{formatPercent(journey.percentage)}</span>
                            </div>
                          </div>
                        ))
                      ) : (
                        <p className="py-4 text-center text-xs text-muted-foreground">
                          {selectedEntryPage ? "No path data for this entry page" : "No path data"}
                        </p>
                      )}
                    </CardContent>
                  </Card>
                </div>
              </TabsContent>

              <TabsContent value="pages" className="space-y-0">
                {bucketData.pages.length ? (
                  <div className="space-y-0">
                    <div className="mb-1 grid grid-cols-[1fr_72px_72px_72px] gap-2 border-b pb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                      <span>Page</span>
                      <span className="text-right">Views</span>
                      <span className="text-right">Visits</span>
                      <span className="text-right">Share</span>
                    </div>
                    {bucketData.pages.map((row) => (
                      <div
                        key={row.urlPath}
                        className="grid grid-cols-[1fr_72px_72px_72px] gap-2 py-1.5 text-xs"
                      >
                        <span className="truncate font-mono">{row.urlPath}</span>
                        <span className="text-right tabular-nums">
                          {formatNumber(row.views, false)}
                        </span>
                        <span className="text-right tabular-nums">
                          {formatNumber(row.visits, false)}
                        </span>
                        <span className="text-right tabular-nums text-muted-foreground">
                          {formatBucketShare(row.visits, bucketData.total)}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="py-4 text-center text-xs text-muted-foreground">
                    No pages found
                  </p>
                )}
              </TabsContent>

              <TabsContent value="sources" className="grid gap-4 lg:grid-cols-2">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium">Sources</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-0">
                    {bucketData.sources.length ? (
                      <>
                        <div className="mb-1 grid grid-cols-[1fr_72px_72px] gap-2 border-b pb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                          <span>Source</span>
                          <span className="text-right">Visits</span>
                          <span className="text-right">Share</span>
                        </div>
                        {bucketData.sources.map((row) => (
                          <div
                            key={row.referrerDomain}
                            className="grid grid-cols-[1fr_72px_72px] gap-2 py-1.5 text-xs"
                          >
                            <span className="truncate">{row.referrerDomain}</span>
                            <span className="text-right tabular-nums">
                              {formatNumber(row.visits, false)}
                            </span>
                            <span className="text-right tabular-nums text-muted-foreground">
                              {formatBucketShare(row.visits, bucketData.total)}
                            </span>
                          </div>
                        ))}
                      </>
                    ) : (
                      <p className="py-4 text-center text-xs text-muted-foreground">
                        No sources found
                      </p>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium">Devices</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-0">
                    {bucketData.devices.length ? (
                      <>
                        <div className="mb-1 grid grid-cols-[1fr_72px_72px] gap-2 border-b pb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                          <span>Browser / Device</span>
                          <span className="text-right">OS</span>
                          <span className="text-right">Visits</span>
                        </div>
                        {bucketData.devices.map((row) => (
                          <div
                            key={`${row.browser}-${row.device}-${row.os}`}
                            className="grid grid-cols-[1fr_72px_72px] gap-2 py-1.5 text-xs"
                          >
                            <span className="truncate">{row.browser} / {row.device}</span>
                            <span className="truncate text-right text-muted-foreground">
                              {row.os}
                            </span>
                            <span className="text-right tabular-nums">
                              {formatNumber(row.visits, false)}
                            </span>
                          </div>
                        ))}
                      </>
                    ) : (
                      <p className="py-4 text-center text-xs text-muted-foreground">
                        No device data
                      </p>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          ) : (
            <p className="py-4 text-center text-xs text-muted-foreground">No visits found</p>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
