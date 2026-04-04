import { useMemo, useState } from "react";
import { useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { MetricCard } from "@/components/data/MetricCard";
import { AreaChart } from "@/components/charts/AreaChart";
import {
  useAnnotations,
  getAnnotationMarkers,
} from "@/components/annotations/AnnotationsManager";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDateParams } from "@/hooks/use-site-query";
import { usePreferencesStore } from "@/stores/preferences";
import { DetailSheet, type DetailKind } from "@/components/overview/DetailSheet";

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

interface OverviewData {
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
  events: Array<{
    eventName: string;
    count: number;
    visitors: number;
    properties: Array<{ key: string; value: string; count: number }>;
  }>;
  browsers: Array<{ value: string; visitors: number }>;
  countries: Array<{ country: string; visitors: number; pageviews: number }>;
  sections: Array<{
    section: string;
    views: number;
    visitors: number;
    pages: number;
  }>;
  channels: Array<{
    channel: string;
    visitors: number;
    pageviews: number;
    bounceRate: number;
    avgDuration: number;
  }>;
}

function useOverviewData(siteId: string) {
  const { params, queryKeyParts } = useDateParams();
  const pageMode = usePreferencesStore((s) => s.pageMode);

  return useQuery<OverviewData>({
    queryKey: ["overview", siteId, pageMode, ...queryKeyParts],
    queryFn: async () => {
      const p = new URLSearchParams(params);
      p.set("mode", pageMode);
      const res = await fetch(`/api/sites/${siteId}/stats?${p}`);
      if (!res.ok) throw new Error("Failed to fetch overview data");
      return res.json();
    },
  });
}

function derivedMetrics(s: StatsBlock | undefined) {
  if (!s) return { bounceRate: null, avgDuration: null, pagesPerVisit: null };
  return {
    bounceRate: s.visits > 0 ? (s.bounces / s.visits) * 100 : null,
    avgDuration: s.visits > 0 ? s.totaltime / s.visits : null,
    pagesPerVisit: s.visits > 0 ? s.pageviews / s.visits : null,
  };
}

function SkeletonRows({ count = 5 }: { count?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-6 w-full" />
      ))}
    </div>
  );
}

const ROW =
  "flex items-center justify-between py-1.5 text-sm cursor-pointer rounded-sm px-1 -mx-1 hover:bg-muted/50 transition-colors";

export function OverviewPage() {
  const params = useParams();
  const siteId = params.siteId as string;
  const { data, isLoading } = useOverviewData(siteId);
  const { data: annotations = [] } = useAnnotations();
  const [detail, setDetail] = useState<DetailKind | null>(null);

  const stats = data?.stats;
  const prev = data?.previousStats;
  const current = derivedMetrics(stats);
  const previous = derivedMetrics(prev);

  const annotationMarkers = useMemo(
    () =>
      data?.timeseries
        ? getAnnotationMarkers(annotations, data.timeseries, "time")
        : [],
    [annotations, data?.timeseries]
  );

  return (
    <div className="space-y-4">
      {/* Metrics Bar */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <MetricCard
          label="Pageviews"
          value={stats?.pageviews ?? null}
          previousValue={prev?.pageviews ?? null}
          tooltip="Total number of pages viewed. Repeated views of the same page are counted."
          loading={isLoading}
        />
        <MetricCard
          label="Visitors"
          value={stats?.visitors ?? null}
          previousValue={prev?.visitors ?? null}
          tooltip="Unique visitors identified by session. One person visiting from two browsers counts as two visitors."
          loading={isLoading}
        />
        <MetricCard
          label="Visits"
          value={stats?.visits ?? null}
          previousValue={prev?.visits ?? null}
          tooltip="Number of browsing sessions. A new visit starts after 30 minutes of inactivity."
          loading={isLoading}
        />
        <MetricCard
          label="Bounce Rate"
          value={current.bounceRate}
          previousValue={previous.bounceRate}
          format="percent"
          tooltip="Percentage of visits with only a single page view. Lower is generally better."
          loading={isLoading}
          invertTrend
        />
        <MetricCard
          label="Avg Duration"
          value={current.avgDuration}
          previousValue={previous.avgDuration}
          format="duration"
          tooltip="Average time spent on the site per visit, measured from first to last pageview."
          loading={isLoading}
        />
        <MetricCard
          label="Pages / Visit"
          value={current.pagesPerVisit}
          previousValue={previous.pagesPerVisit}
          tooltip="Average number of pages viewed during a single visit."
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
              comparisonData={data.previousTimeseries}
              comparisonKeys={["pageviews", "visitors"]}
              annotations={annotationMarkers}
            />
          ) : null}
        </CardContent>
      </Card>

      {/* Sections */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">
            Top Sections
          </CardTitle>
          <CardDescription className="text-xs">
            Traffic grouped by URL path prefix
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <SkeletonRows />
          ) : (
            <div className="space-y-0">
              <div className="flex items-center justify-between border-b pb-1.5 mb-1 text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
                <span>Section</span>
                <div className="flex gap-4 text-right">
                  <span className="w-16">Visitors</span>
                  <span className="w-16">Views</span>
                  <span className="w-12">Pages</span>
                </div>
              </div>
              {data?.sections.map((s) => (
                <div
                  key={s.section}
                  className={ROW}
                  onClick={() => setDetail({ type: "section", value: s.section })}
                >
                  <span className="truncate font-mono text-xs">
                    {s.section}
                  </span>
                  <div className="flex gap-4 text-right tabular-nums">
                    <span className="w-16 text-muted-foreground">
                      {s.visitors.toLocaleString()}
                    </span>
                    <span className="w-16 font-medium">
                      {s.views.toLocaleString()}
                    </span>
                    <span className="w-12 text-muted-foreground">
                      {s.pages.toLocaleString()}
                    </span>
                  </div>
                </div>
              ))}
              {(!data?.sections || data.sections.length === 0) && (
                <p className="py-4 text-center text-xs text-muted-foreground">
                  No section data
                </p>
              )}
            </div>
          )}
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
              <SkeletonRows />
            ) : (
              <div className="space-y-0">
                <div className="flex items-center justify-between border-b pb-1.5 mb-1 text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
                  <span>Page</span>
                  <div className="flex gap-4 text-right">
                    <span className="w-16">Visitors</span>
                    <span className="w-16">Views</span>
                  </div>
                </div>
                {data?.pages.map((page) => (
                  <div
                    key={page.urlPath}
                    className={ROW}
                    onClick={() => setDetail({ type: "page", value: page.urlPath })}
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
              <SkeletonRows />
            ) : (
              <div className="space-y-0">
                <div className="flex items-center justify-between border-b pb-1.5 mb-1 text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
                  <span>Source</span>
                  <span>Visitors</span>
                </div>
                {data?.referrers.map((ref) => (
                  <div
                    key={ref.referrerDomain}
                    className={ROW}
                    onClick={() => setDetail({ type: "referrer", value: ref.referrerDomain })}
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

        {/* Channels */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Channels</CardTitle>
            <CardDescription className="text-xs">
              Traffic channels breakdown
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <SkeletonRows />
            ) : (
              <div className="space-y-0">
                <div className="flex items-center justify-between border-b pb-1.5 mb-1 text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
                  <span>Channel</span>
                  <div className="flex gap-4 text-right">
                    <span className="w-16">Visitors</span>
                    <span className="w-16">Bounce</span>
                  </div>
                </div>
                {data?.channels?.map((ch) => (
                  <div
                    key={ch.channel}
                    className={ROW}
                  >
                    <span className="truncate">{ch.channel}</span>
                    <div className="flex gap-4 text-right tabular-nums">
                      <span className="w-16 font-medium">
                        {ch.visitors.toLocaleString()}
                      </span>
                      <span className="w-16 text-muted-foreground">
                        {ch.bounceRate.toFixed(1)}%
                      </span>
                    </div>
                  </div>
                ))}
                {(!data?.channels || data.channels.length === 0) && (
                  <p className="py-4 text-center text-xs text-muted-foreground">
                    No channel data
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
              <SkeletonRows />
            ) : (
              <div className="space-y-0">
                <div className="flex items-center justify-between border-b pb-1.5 mb-1 text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
                  <span>Event</span>
                  <span>Count</span>
                </div>
                {data?.events.map((evt) => (
                  <div
                    key={evt.eventName}
                    className="cursor-pointer rounded-sm px-1 -mx-1 hover:bg-muted/50 transition-colors"
                    onClick={() => setDetail({ type: "event", value: evt.eventName })}
                  >
                    <div className="flex items-center justify-between py-1.5 text-sm">
                      <span className="truncate font-mono text-xs">
                        {evt.eventName}
                      </span>
                      <span className="tabular-nums font-medium">
                        {evt.count.toLocaleString()}
                      </span>
                    </div>
                    {evt.properties && evt.properties.length > 0 && (
                      <div className="pb-1.5 pl-2 text-[11px] text-muted-foreground leading-tight">
                        {Object.entries(
                          evt.properties.reduce<Record<string, Array<{ value: string; count: number }>>>(
                            (acc, p) => {
                              if (!acc[p.key]) acc[p.key] = [];
                              acc[p.key].push({ value: p.value, count: p.count });
                              return acc;
                            },
                            {},
                          ),
                        ).map(([key, values]) => (
                          <div key={key}>
                            {key}: {values.map((v, i) => (
                              <span key={i}>
                                {i > 0 && ", "}
                                {v.value} ({v.count.toLocaleString()})
                              </span>
                            ))}
                          </div>
                        ))}
                      </div>
                    )}
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
              <SkeletonRows />
            ) : (
              <div className="space-y-0">
                <div className="flex items-center justify-between border-b pb-1.5 mb-1 text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
                  <span>Browser</span>
                  <span>Visitors</span>
                </div>
                {data?.browsers.map((b) => (
                  <div
                    key={b.value}
                    className={ROW}
                    onClick={() => setDetail({ type: "browser", value: b.value })}
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

      {/* Detail slide-out panel */}
      <DetailSheet detail={detail} onClose={() => setDetail(null)} />
    </div>
  );
}
