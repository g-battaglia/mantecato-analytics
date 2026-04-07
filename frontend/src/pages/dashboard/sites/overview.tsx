import { useMemo, useState } from "react";
import { useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { MetricCard } from "@/components/data/MetricCard";
import { AreaChart } from "@/components/charts/AreaChart";
import { WorldMap } from "@/components/charts/WorldMap";
import { TrafficHeatmap } from "@/components/charts/TrafficHeatmap";
import {
  useAnnotations,
  getAnnotationMarkers,
} from "@/components/annotations/AnnotationsManager";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDateParams } from "@/hooks/use-site-query";
import { usePreferencesStore } from "@/stores/preferences";
import { useFiltersStore } from "@/stores/filters";
import { apiFetch } from "@/lib/api";

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
  referrers: Array<{ referrerDomain: string; visitors: number; pageviews: number }>;
  events: Array<{
    eventName: string;
    count: number;
    visitors: number;
    properties: Array<{ key: string; value: string; count: number }>;
  }>;
  browsers: Array<{ value: string; visitors: number }>;
  os: Array<{ value: string; visitors: number }>;
  devices: Array<{ value: string; visitors: number }>;
  countries: Array<{ country: string; visitors: number; pageviews: number }>;
  regions: Array<{ region: string | null; visitors: number; pageviews: number }>;
  cities: Array<{ city: string | null; visitors: number; pageviews: number }>;
  sections: Array<{ section: string; views: number; visitors: number; pages: number }>;
  entryPages: Array<{ urlPath: string; entries: number; visitors: number }>;
  exitPages: Array<{ urlPath: string; exits: number; visitors: number }>;
  heatmap: Array<{ dayOfWeek: number; hour: number; pageviews: number; visitors: number }>;
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
  const urlNormalization = usePreferencesStore((s) => s.urlNormalization);

  return useQuery<OverviewData>({
    queryKey: ["overview", siteId, pageMode, urlNormalization, ...queryKeyParts],
    queryFn: async () => {
      const p = new URLSearchParams(params);
      p.set("mode", pageMode);
      p.set("normalize", urlNormalization);
      const res = await apiFetch(`/api/sites/${siteId}/stats?${p}`);
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
  const addFilter = useFiltersStore((s) => s.addFilter);

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

  const totalViews = data?.sections.reduce((s, x) => s + x.views, 0) ?? 0;
  const totalPageVisitors = data?.pages.reduce((s, x) => s + x.visitors, 0) ?? 0;
  const totalRefVisitors = data?.referrers.reduce((s, x) => s + x.visitors, 0) ?? 0;
  const totalEventCount = data?.events.reduce((s, x) => s + x.count, 0) ?? 0;
  const totalBrowserVisitors = data?.browsers.reduce((s, x) => s + x.visitors, 0) ?? 0;
  const totalOsVisitors = data?.os?.reduce((s, x) => s + x.visitors, 0) ?? 0;
  const totalDeviceVisitors = data?.devices?.reduce((s, x) => s + x.visitors, 0) ?? 0;
  const totalChannelVisitors = data?.channels?.reduce((s, x) => s + x.visitors, 0) ?? 0;
  const totalEntries = data?.entryPages?.reduce((s, x) => s + x.entries, 0) ?? 0;
  const totalExits = data?.exitPages?.reduce((s, x) => s + x.exits, 0) ?? 0;
  const totalRegionVisitors = data?.regions?.reduce((s, x) => s + x.visitors, 0) ?? 0;
  const totalCityVisitors = data?.cities?.reduce((s, x) => s + x.visitors, 0) ?? 0;

  const pct = (n: number, total: number) =>
    total > 0 ? `${((n / total) * 100).toFixed(1)}%` : "—";

  return (
    <div className="space-y-4">
      {/* Metrics Bar */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <MetricCard label="Pageviews" value={stats?.pageviews ?? null} previousValue={prev?.pageviews ?? null} tooltip="Total number of pages viewed" loading={isLoading} />
        <MetricCard label="Visitors" value={stats?.visitors ?? null} previousValue={prev?.visitors ?? null} tooltip="Unique visitors by session" loading={isLoading} />
        <MetricCard label="Visits" value={stats?.visits ?? null} previousValue={prev?.visits ?? null} tooltip="Browsing sessions (30min inactivity)" loading={isLoading} />
        <MetricCard label="Bounce Rate" value={current.bounceRate} previousValue={previous.bounceRate} format="percent" tooltip="Single-page visits" loading={isLoading} invertTrend />
        <MetricCard label="Avg Duration" value={current.avgDuration} previousValue={previous.avgDuration} format="duration" tooltip="Average time per visit" loading={isLoading} />
        <MetricCard label="Pages / Visit" value={current.pagesPerVisit} previousValue={previous.pagesPerVisit} tooltip="Pages per visit" loading={isLoading} />
      </div>

      {/* Time Series */}
      <Card>
        <CardContent className="pt-4">
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

      {/* 2-column panels */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Pages: Sections / Pages / Entry URLs / Exit URLs */}
        <Card>
          <CardContent className="pt-4">
            <PanelTabs tabs={[
              { label: "Sections", content: (
                <ListTable loading={isLoading}
                  headers={["Section", "Visitors", "Views", "%"]}
                  widths={["flex-1", "w-16", "w-16", "w-14"]}
                  rows={data?.sections.map((s) => ({
                    key: s.section, label: s.section, mono: true,
                    onClick: () => {
                      const prefix = s.section.replace(/\/:id/g, "");
                      addFilter({ column: "url_path", operator: "starts_with", value: prefix || "/" });
                    },
                    values: [
                      { v: s.visitors.toLocaleString(), muted: true },
                      { v: s.views.toLocaleString(), bold: true },
                      { v: pct(s.views, totalViews), muted: true },
                    ],
                  })) ?? []}
                  empty="No section data"
                />
              )},
              { label: "Pages", content: (
                <ListTable loading={isLoading}
                  headers={["Page", "Visitors", "Views", "%"]}
                  widths={["flex-1", "w-16", "w-16", "w-14"]}
                  rows={data?.pages.map((p) => ({
                    key: p.urlPath, label: p.urlPath, mono: true,
                    onClick: () => addFilter({ column: "url_path", operator: "eq", value: p.urlPath }),
                    values: [
                      { v: p.visitors.toLocaleString(), muted: true },
                      { v: p.views.toLocaleString(), bold: true },
                      { v: pct(p.visitors, totalPageVisitors), muted: true },
                    ],
                  })) ?? []}
                  empty="No page data"
                />
              )},
              { label: "Entry URLs", content: (
                <ListTable loading={isLoading}
                  headers={["Entry Page", "Entries", "%"]}
                  widths={["flex-1", "w-16", "w-14"]}
                  rows={data?.entryPages?.map((p) => ({
                    key: p.urlPath, label: p.urlPath, mono: true,
                    onClick: () => addFilter({ column: "url_path", operator: "eq", value: p.urlPath }),
                    values: [
                      { v: p.entries.toLocaleString(), bold: true },
                      { v: pct(p.entries, totalEntries), muted: true },
                    ],
                  })) ?? []}
                  empty="No entry page data"
                />
              )},
              { label: "Exit URLs", content: (
                <ListTable loading={isLoading}
                  headers={["Exit Page", "Exits", "%"]}
                  widths={["flex-1", "w-16", "w-14"]}
                  rows={data?.exitPages?.map((p) => ({
                    key: p.urlPath, label: p.urlPath, mono: true,
                    onClick: () => addFilter({ column: "url_path", operator: "eq", value: p.urlPath }),
                    values: [
                      { v: p.exits.toLocaleString(), bold: true },
                      { v: pct(p.exits, totalExits), muted: true },
                    ],
                  })) ?? []}
                  empty="No exit page data"
                />
              )},
            ]} />
          </CardContent>
        </Card>

        {/* Sources: Referrers / Channels */}
        <Card>
          <CardContent className="pt-4">
            <PanelTabs tabs={[
              { label: "Referrers", content: (
                <ListTable loading={isLoading}
                  headers={["Source", "Visitors", "%"]}
                  widths={["flex-1", "w-16", "w-14"]}
                  rows={data?.referrers.map((r) => ({
                    key: r.referrerDomain, label: r.referrerDomain,
                    onClick: () => addFilter({ column: "referrer_domain", operator: "eq", value: r.referrerDomain }),
                    values: [
                      { v: r.visitors.toLocaleString(), bold: true },
                      { v: pct(r.visitors, totalRefVisitors), muted: true },
                    ],
                  })) ?? []}
                  empty="No referrer data"
                />
              )},
              { label: "Channels", content: (
                <ListTable loading={isLoading}
                  headers={["Channel", "Visitors", "%", "Bounce"]}
                  widths={["flex-1", "w-16", "w-14", "w-16"]}
                  rows={data?.channels?.map((ch) => ({
                    key: ch.channel, label: ch.channel,
                    values: [
                      { v: ch.visitors.toLocaleString(), bold: true },
                      { v: pct(ch.visitors, totalChannelVisitors), muted: true },
                      { v: `${ch.bounceRate.toFixed(1)}%`, muted: true },
                    ],
                  })) ?? []}
                  empty="No channel data"
                />
              )},
            ]} />
          </CardContent>
        </Card>

        {/* Environment: Browser / OS / Devices */}
        <Card>
          <CardContent className="pt-4">
            <PanelTabs tabs={[
              { label: "Browser", content: (
                <ListTable loading={isLoading}
                  headers={["Browser", "Visitors", "%"]}
                  widths={["flex-1", "w-16", "w-14"]}
                  rows={data?.browsers.map((b) => ({
                    key: b.value, label: b.value,
                    onClick: () => addFilter({ column: "browser", operator: "eq", value: b.value }),
                    values: [
                      { v: b.visitors.toLocaleString(), bold: true },
                      { v: pct(b.visitors, totalBrowserVisitors), muted: true },
                    ],
                  })) ?? []}
                  empty="No browser data"
                />
              )},
              { label: "OS", content: (
                <ListTable loading={isLoading}
                  headers={["OS", "Visitors", "%"]}
                  widths={["flex-1", "w-16", "w-14"]}
                  rows={data?.os?.map((o) => ({
                    key: o.value, label: o.value,
                    onClick: () => addFilter({ column: "os", operator: "eq", value: o.value }),
                    values: [
                      { v: o.visitors.toLocaleString(), bold: true },
                      { v: pct(o.visitors, totalOsVisitors), muted: true },
                    ],
                  })) ?? []}
                  empty="No OS data"
                />
              )},
              { label: "Devices", content: (
                <ListTable loading={isLoading}
                  headers={["Device", "Visitors", "%"]}
                  widths={["flex-1", "w-16", "w-14"]}
                  rows={data?.devices?.map((d) => ({
                    key: d.value, label: d.value,
                    onClick: () => addFilter({ column: "device", operator: "eq", value: d.value }),
                    values: [
                      { v: d.visitors.toLocaleString(), bold: true },
                      { v: pct(d.visitors, totalDeviceVisitors), muted: true },
                    ],
                  })) ?? []}
                  empty="No device data"
                />
              )},
            ]} />
          </CardContent>
        </Card>

        {/* Location: Countries / Regions / Cities */}
        <Card>
          <CardContent className="pt-4">
            <PanelTabs tabs={[
              { label: "Countries", content: (
                <ListTable loading={isLoading}
                  headers={["Country", "Visitors", "%"]}
                  widths={["flex-1", "w-16", "w-14"]}
                  rows={data?.countries.map((c) => ({
                    key: c.country, label: c.country || "(unknown)",
                    onClick: () => addFilter({ column: "country", operator: "eq", value: c.country }),
                    values: [
                      { v: c.visitors.toLocaleString(), bold: true },
                      { v: pct(c.visitors, stats?.visitors ?? 0), muted: true },
                    ],
                  })) ?? []}
                  empty="No country data"
                />
              )},
              { label: "Regions", content: (
                <ListTable loading={isLoading}
                  headers={["Region", "Visitors", "%"]}
                  widths={["flex-1", "w-16", "w-14"]}
                  rows={data?.regions?.map((r) => ({
                    key: r.region ?? "unknown", label: r.region || "(unknown)",
                    onClick: () => r.region ? addFilter({ column: "region", operator: "eq", value: r.region }) : undefined,
                    values: [
                      { v: r.visitors.toLocaleString(), bold: true },
                      { v: pct(r.visitors, totalRegionVisitors), muted: true },
                    ],
                  })) ?? []}
                  empty="No region data"
                />
              )},
              { label: "Cities", content: (
                <ListTable loading={isLoading}
                  headers={["City", "Visitors", "%"]}
                  widths={["flex-1", "w-16", "w-14"]}
                  rows={data?.cities?.map((c) => ({
                    key: c.city ?? "unknown", label: c.city || "(unknown)",
                    onClick: () => c.city ? addFilter({ column: "city", operator: "eq", value: c.city }) : undefined,
                    values: [
                      { v: c.visitors.toLocaleString(), bold: true },
                      { v: pct(c.visitors, totalCityVisitors), muted: true },
                    ],
                  })) ?? []}
                  empty="No city data"
                />
              )},
            ]} />
          </CardContent>
        </Card>
      </div>

      {/* World Map — full width */}
      <Card>
        <CardContent className="pt-4">
          {isLoading ? (
            <Skeleton className="h-[400px] w-full" />
          ) : data?.countries ? (
            <WorldMap
              data={data.countries}
              height={400}
              onCountryClick={(code) => addFilter({ column: "country", operator: "eq", value: code })}
            />
          ) : null}
        </CardContent>
      </Card>

      {/* Events + Traffic Heatmap — side by side */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardContent className="pt-4">
            <div className="mb-3 text-sm font-medium">Traffic</div>
            {isLoading ? (
              <Skeleton className="h-[340px] w-full" />
            ) : data?.heatmap ? (
              <TrafficHeatmap data={data.heatmap} />
            ) : (
              <p className="py-8 text-center text-xs text-muted-foreground">No traffic data</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <PanelTabs tabs={[
              { label: "Events", content: (
                <ListTable loading={isLoading}
                  headers={["Event", "Count", "Visitors", "%"]}
                  widths={["flex-1", "w-16", "w-16", "w-14"]}
                  rows={data?.events.map((evt) => ({
                    key: evt.eventName, label: evt.eventName, mono: true,
                    onClick: () => addFilter({ column: "event_name", operator: "eq", value: evt.eventName }),
                    values: [
                      { v: evt.count.toLocaleString(), bold: true },
                      { v: evt.visitors.toLocaleString(), muted: true },
                      { v: pct(evt.count, totalEventCount), muted: true },
                    ],
                  })) ?? []}
                  empty="No event data"
                />
              )},
              { label: "Properties", content: (
                <div className="space-y-4">
                  {isLoading ? <SkeletonRows /> : (
                    <>
                      {data?.events.flatMap((evt) =>
                        (evt.properties ?? []).length > 0 ? [evt] : []
                      ).map((evt) => {
                        const grouped = evt.properties.reduce<Record<string, Array<{ value: string; count: number }>>>(
                          (acc, p) => { if (!acc[p.key]) acc[p.key] = []; acc[p.key].push({ value: p.value, count: p.count }); return acc; }, {},
                        );
                        return (
                          <div key={evt.eventName} className="rounded-lg border p-3">
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-sm font-medium font-mono">{evt.eventName}</span>
                              <span className="text-xs text-muted-foreground tabular-nums">{evt.count.toLocaleString()} total</span>
                            </div>
                            <div className="space-y-3">
                              {Object.entries(grouped).map(([key, values]) => {
                                const keyMax = Math.max(...values.map((v) => v.count));
                                return (
                                  <div key={key}>
                                    <div className="text-xs font-medium text-muted-foreground mb-1">{key}</div>
                                    <div className="space-y-1">
                                      {values.map((v) => (
                                        <div key={v.value} className="flex items-center gap-2 text-sm">
                                          <span className="min-w-[100px] truncate" title={v.value}>{v.value}</span>
                                          <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                                            <div
                                              className="h-full rounded-full bg-primary/60"
                                              style={{ width: `${(v.count / keyMax) * 100}%` }}
                                            />
                                          </div>
                                          <span className="w-12 text-right tabular-nums text-xs text-muted-foreground">
                                            {v.count.toLocaleString()}
                                          </span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        );
                      })}
                      {(!data?.events.some((e) => e.properties?.length > 0)) && (
                        <p className="py-4 text-center text-xs text-muted-foreground">No event properties</p>
                      )}
                    </>
                  )}
                </div>
              )},
            ]} />
          </CardContent>
        </Card>
      </div>
  );
}

/* ── Reusable sub-components ── */

function PanelTabs({ tabs }: { tabs: Array<{ label: string; content: React.ReactNode }> }) {
  const [active, setActive] = useState(0);
  return (
    <div>
      {tabs.length > 1 && (
        <div className="flex gap-4 border-b mb-3">
          {tabs.map((tab, i) => (
            <button
              key={tab.label}
              className={`pb-2 text-sm font-medium transition-colors ${
                i === active
                  ? "border-b-2 border-foreground text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              onClick={() => setActive(i)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}
      {tabs.length === 1 && (
        <div className="mb-3 text-sm font-medium">{tabs[0].label}</div>
      )}
      {tabs[active]?.content}
    </div>
  );
}

interface ListRow {
  key: string;
  label: string;
  mono?: boolean;
  onClick?: () => void;
  values: Array<{ v: string; bold?: boolean; muted?: boolean }>;
}

function ListTable({
  loading, headers, widths, rows, empty,
}: {
  loading: boolean;
  headers: string[];
  widths: string[];
  rows: ListRow[];
  empty: string;
}) {
  if (loading) return <SkeletonRows />;
  return (
    <div className="space-y-0">
      <div className="flex items-center justify-between border-b pb-1.5 mb-1 text-xs font-medium text-muted-foreground uppercase tracking-wider">
        <span>{headers[0]}</span>
        <div className="flex gap-4 text-right">
          {headers.slice(1).map((h, i) => (
            <span key={h} className={widths[i + 1]}>{h}</span>
          ))}
        </div>
      </div>
      {rows.map((row) => (
        <div key={row.key} className={ROW} onClick={row.onClick}>
          <span className={`truncate ${row.mono ? "font-mono text-sm" : ""}`} title={row.label}>
            {row.label}
          </span>
          <div className="flex gap-4 text-right tabular-nums">
            {row.values.map((val, i) => (
              <span key={i} className={`${widths[i + 1]} ${val.bold ? "font-medium" : ""} ${val.muted ? "text-muted-foreground" : ""}`}>
                {val.v}
              </span>
            ))}
          </div>
        </div>
      ))}
      {rows.length === 0 && (
        <p className="py-4 text-center text-xs text-muted-foreground">{empty}</p>
      )}
    </div>
  );
}
