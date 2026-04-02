import { useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { useDateParams } from "@/hooks/use-site-query";
import { MetricCard } from "@/components/data/MetricCard";
import { BarChart } from "@/components/charts/BarChart";
import { DataTable, numericColumn, percentColumn } from "@/components/data/DataTable";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDuration, formatPercent } from "@/lib/format";
import type { ColumnDef } from "@tanstack/react-table";

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

function useEngagementData(siteId: string) {
  const { params, queryKeyParts } = useDateParams();
  return useQuery<EngagementData>({
    queryKey: ["engagement", siteId, ...queryKeyParts],
    queryFn: async () => {
      const res = await fetch(`/api/sites/${siteId}/engagement?${params}`);
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

  const p = data?.percentiles;

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
    </div>
  );
}
