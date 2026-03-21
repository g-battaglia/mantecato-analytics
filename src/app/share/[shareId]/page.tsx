"use client";

import { useState, useMemo } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { MetricCard } from "@/components/data/MetricCard";
import { AreaChart } from "@/components/charts/AreaChart";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/lib/theme";

const DATE_PRESETS = [
  { value: "24h", label: "Last 24 hours" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
  { value: "1y", label: "Last year" },
] as const;

const GRANULARITY_MAP: Record<string, string> = {
  "24h": "hour",
  "7d": "day",
  "30d": "day",
  "90d": "week",
  "1y": "month",
};

interface StatsBlock {
  pageviews: number;
  visitors: number;
  visits: number;
  bounces: number;
  totaltime: number;
}

interface TimeSeriesRow {
  time: string;
  pageviews: number;
  visitors: number;
}

interface ShareData {
  website: { name: string; domain: string | null };
  stats: StatsBlock;
  previousStats: StatsBlock;
  timeseries: TimeSeriesRow[];
  previousTimeseries: TimeSeriesRow[];
  pages: Array<{ urlPath: string; views: number; visitors: number }>;
  referrers: Array<{
    referrerDomain: string;
    visitors: number;
    pageviews: number;
  }>;
  events: Array<{ eventName: string; count: number; visitors: number }>;
  browsers: Array<{ value: string; visitors: number }>;
  countries: Array<{ country: string; visitors: number; pageviews: number }>;
}

function derivedMetrics(s: StatsBlock | undefined) {
  if (!s) return { bounceRate: null, avgDuration: null, pagesPerVisit: null };
  return {
    bounceRate: s.visits > 0 ? (s.bounces / s.visits) * 100 : null,
    avgDuration: s.visits > 0 ? s.totaltime / s.visits : null,
    pagesPerVisit: s.visits > 0 ? s.pageviews / s.visits : null,
  };
}

export default function SharePage() {
  const params = useParams();
  const shareId = params.shareId as string;
  const [range, setRange] = useState("30d");
  const { resolvedTheme, setTheme } = useTheme();

  const granularity = GRANULARITY_MAP[range] || "day";

  const { data, isLoading, error } = useQuery<ShareData>({
    queryKey: ["share", shareId, range],
    queryFn: async () => {
      const res = await fetch(
        `/api/share/${shareId}/stats?range=${range}&granularity=${granularity}`
      );
      if (!res.ok) {
        if (res.status === 404) throw new Error("not_found");
        throw new Error("Failed to fetch");
      }
      return res.json();
    },
  });

  const stats = data?.stats;
  const prev = data?.previousStats;
  const current = derivedMetrics(stats);
  const previous = derivedMetrics(prev);

  // Not-found state
  if (error?.message === "not_found") {
    return (
      <div className="flex min-h-svh items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-semibold">Not Found</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            This shared dashboard doesn&apos;t exist or has been disabled.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">
            {data?.website.name ?? <Skeleton className="inline-block h-6 w-40" />}
          </h1>
          {data?.website.domain && (
            <p className="text-sm text-muted-foreground">
              {data.website.domain}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Select value={range} onValueChange={setRange}>
            <SelectTrigger className="w-[160px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {DATE_PRESETS.map((p) => (
                <SelectItem key={p.value} value={p.value}>
                  {p.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() =>
              setTheme(resolvedTheme === "dark" ? "light" : "dark")
            }
          >
            <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
            <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
            <span className="sr-only">Toggle theme</span>
          </Button>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <MetricCard
          label="Pageviews"
          value={stats?.pageviews ?? null}
          previousValue={prev?.pageviews ?? null}
          tooltip="Total number of pages viewed."
          loading={isLoading}
        />
        <MetricCard
          label="Visitors"
          value={stats?.visitors ?? null}
          previousValue={prev?.visitors ?? null}
          tooltip="Unique visitors identified by session."
          loading={isLoading}
        />
        <MetricCard
          label="Visits"
          value={stats?.visits ?? null}
          previousValue={prev?.visits ?? null}
          tooltip="Number of browsing sessions."
          loading={isLoading}
        />
        <MetricCard
          label="Bounce Rate"
          value={current.bounceRate}
          previousValue={previous.bounceRate}
          format="percent"
          tooltip="Percentage of visits with only a single page view."
          loading={isLoading}
          invertTrend
        />
        <MetricCard
          label="Avg Duration"
          value={current.avgDuration}
          previousValue={previous.avgDuration}
          format="duration"
          tooltip="Average time spent on the site per visit."
          loading={isLoading}
        />
        <MetricCard
          label="Pages / Visit"
          value={current.pagesPerVisit}
          previousValue={previous.pagesPerVisit}
          tooltip="Average pages viewed per visit."
          loading={isLoading}
        />
      </div>

      {/* Time Series */}
      <Card className="mt-4">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Traffic</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-[300px] w-full" />
          ) : data?.timeseries ? (
            <AreaChart
              data={data.timeseries}
              xKey="time"
              yKeys={["pageviews", "visitors"]}
              labels={{ pageviews: "Pageviews", visitors: "Visitors" }}
              comparisonData={data.previousTimeseries}
              comparisonKeys={["pageviews", "visitors"]}
            />
          ) : null}
        </CardContent>
      </Card>

      {/* Panels */}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        {/* Top Pages */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Top Pages</CardTitle>
            <CardDescription className="text-xs">
              Most visited pages
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-6 w-full" />
                ))}
              </div>
            ) : (
              <div className="space-y-1">
                {data?.pages.map((page) => (
                  <div
                    key={page.urlPath}
                    className="flex items-center justify-between py-1 text-sm"
                  >
                    <span className="truncate font-mono text-xs">
                      {page.urlPath}
                    </span>
                    <div className="flex gap-4 text-right tabular-nums">
                      <span className="w-16 text-muted-foreground">
                        {page.visitors.toLocaleString()}
                      </span>
                      <span className="w-16 font-medium">
                        {page.views.toLocaleString()}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Top Referrers */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Top Referrers
            </CardTitle>
            <CardDescription className="text-xs">
              Traffic sources
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-6 w-full" />
                ))}
              </div>
            ) : (
              <div className="space-y-1">
                {data?.referrers.map((ref) => (
                  <div
                    key={ref.referrerDomain}
                    className="flex items-center justify-between py-1 text-sm"
                  >
                    <span className="truncate">{ref.referrerDomain}</span>
                    <span className="tabular-nums font-medium">
                      {ref.visitors.toLocaleString()}
                    </span>
                  </div>
                ))}
                {(!data?.referrers || data.referrers.length === 0) && (
                  <p className="py-4 text-center text-xs text-muted-foreground">
                    No referrer data
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Top Events */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Top Events</CardTitle>
            <CardDescription className="text-xs">
              Custom events tracked
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-6 w-full" />
                ))}
              </div>
            ) : (
              <div className="space-y-1">
                {data?.events.map((evt) => (
                  <div
                    key={evt.eventName}
                    className="flex items-center justify-between py-1 text-sm"
                  >
                    <span className="truncate font-mono text-xs">
                      {evt.eventName}
                    </span>
                    <span className="tabular-nums font-medium">
                      {evt.count.toLocaleString()}
                    </span>
                  </div>
                ))}
                {(!data?.events || data.events.length === 0) && (
                  <p className="py-4 text-center text-xs text-muted-foreground">
                    No event data
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Countries */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Countries</CardTitle>
            <CardDescription className="text-xs">
              Visitor countries
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-6 w-full" />
                ))}
              </div>
            ) : (
              <div className="space-y-1">
                {data?.countries.map((c) => (
                  <div
                    key={c.country}
                    className="flex items-center justify-between py-1 text-sm"
                  >
                    <span className="truncate">{c.country}</span>
                    <span className="tabular-nums font-medium">
                      {c.visitors.toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Footer */}
      <div className="mt-8 text-center text-xs text-muted-foreground">
        Powered by{" "}
        <span className="font-medium text-foreground">Mantecato</span>
      </div>
    </div>
  );
}
