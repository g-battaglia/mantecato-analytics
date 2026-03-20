"use client";

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
import { useDateParams } from "@/hooks/use-site-query";

interface OverviewData {
  stats: {
    pageviews: number;
    visitors: number;
    visits: number;
    bounces: number;
    totaltime: number;
  };
  timeseries: Array<{
    time: string;
    pageviews: number;
    visitors: number;
  }>;
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

function useOverviewData(siteId: string) {
  const { params, queryKeyParts } = useDateParams();

  return useQuery<OverviewData>({
    queryKey: ["overview", siteId, ...queryKeyParts],
    queryFn: async () => {
      const res = await fetch(`/api/sites/${siteId}/stats?${params}`);
      if (!res.ok) throw new Error("Failed to fetch overview data");
      return res.json();
    },
  });
}

export default function SiteOverviewPage() {
  const params = useParams();
  const siteId = params.siteId as string;
  const { data, isLoading } = useOverviewData(siteId);

  const stats = data?.stats;
  const bounceRate =
    stats && stats.visits > 0
      ? (stats.bounces / stats.visits) * 100
      : null;
  const avgDuration =
    stats && stats.visits > 0 ? stats.totaltime / stats.visits : null;
  const pagesPerVisit =
    stats && stats.visits > 0 ? stats.pageviews / stats.visits : null;

  return (
    <div className="space-y-4">
      {/* Metrics Bar */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <MetricCard
          label="Pageviews"
          value={stats?.pageviews ?? null}
          loading={isLoading}
        />
        <MetricCard
          label="Visitors"
          value={stats?.visitors ?? null}
          loading={isLoading}
        />
        <MetricCard
          label="Visits"
          value={stats?.visits ?? null}
          loading={isLoading}
        />
        <MetricCard
          label="Bounce Rate"
          value={bounceRate}
          format="percent"
          loading={isLoading}
          invertTrend
        />
        <MetricCard
          label="Avg Duration"
          value={avgDuration}
          format="duration"
          loading={isLoading}
        />
        <MetricCard
          label="Pages / Visit"
          value={pagesPerVisit}
          loading={isLoading}
        />
      </div>

      {/* Time Series Chart */}
      <Card>
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
            />
          ) : null}
        </CardContent>
      </Card>

      {/* Bottom Panels */}
      <div className="grid gap-4 lg:grid-cols-2">
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

        {/* Browsers */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Browsers</CardTitle>
            <CardDescription className="text-xs">
              Visitor browsers
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
                {data?.browsers.map((b) => (
                  <div
                    key={b.value}
                    className="flex items-center justify-between py-1 text-sm"
                  >
                    <span className="truncate">{b.value}</span>
                    <span className="tabular-nums font-medium">
                      {b.visitors.toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
