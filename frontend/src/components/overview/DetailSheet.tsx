import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { AreaChart } from "@/components/charts/AreaChart";
import { Skeleton } from "@/components/ui/skeleton";
import { useDateParams } from "@/hooks/use-site-query";
import { formatNumber } from "@/lib/format";
import { apiFetch } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────

export type DetailKind =
  | { type: "section"; value: string }
  | { type: "page"; value: string }
  | { type: "referrer"; value: string }
  | { type: "event"; value: string }
  | { type: "browser"; value: string };

interface Props {
  detail: DetailKind | null;
  onClose: () => void;
}

// ── Helpers ───────────────────────────────────────────────────────

function StatRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="tabular-nums font-medium">
        {typeof value === "number" ? formatNumber(value) : value}
      </span>
    </div>
  );
}

function MiniTable({
  rows,
  labelKey,
  valueKey,
  valueLabel,
  mono = false,
}: {
  rows: Record<string, unknown>[];
  labelKey: string;
  valueKey: string;
  valueLabel: string;
  mono?: boolean;
}) {
  if (!rows.length) return null;
  return (
    <div className="space-y-0">
      <div className="flex items-center justify-between border-b pb-1.5 mb-1 text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
        <span>{labelKey === "urlPath" ? "Page" : labelKey === "referrerDomain" ? "Source" : "Name"}</span>
        <span>{valueLabel}</span>
      </div>
      {rows.map((row, i) => (
        <div
          key={i}
          className="flex items-center justify-between py-1 text-sm"
        >
          <span className={`truncate mr-4 ${mono ? "font-mono text-xs" : ""}`}>
            {String(row[labelKey] ?? "")}
          </span>
          <span className="tabular-nums font-medium shrink-0">
            {formatNumber(Number(row[valueKey] ?? 0))}
          </span>
        </div>
      ))}
    </div>
  );
}

// ── Data Hooks ────────────────────────────────────────────────────

function useDetailData(detail: DetailKind | null) {
  const { siteId } = useParams() as { siteId: string };
  const { params } = useDateParams();

  // Page detail
  const page = useQuery({
    queryKey: ["detail", "page", detail?.type === "page" ? detail.value : "", siteId, params.toString()],
    enabled: detail?.type === "page",
    queryFn: async () => {
      const p = new URLSearchParams(params);
      p.set("page", detail!.value);
      const res = await apiFetch(`/api/sites/${siteId}/pages?${p}`);
      if (!res.ok) throw new Error("fetch failed");
      return res.json() as Promise<{
        timeseries: Array<{ time: string; views: number; visitors: number }>;
        referrers: Array<{ referrerDomain: string; visitors: number; views: number }>;
        nextPages: Array<{ urlPath: string; count: number; percentage: number }>;
        timeDistribution: Array<{ bucket: string; count: number }>;
      }>;
    },
  });

  // Event detail
  const event = useQuery({
    queryKey: ["detail", "event", detail?.type === "event" ? detail.value : "", siteId, params.toString()],
    enabled: detail?.type === "event",
    queryFn: async () => {
      const p = new URLSearchParams(params);
      p.set("event", detail!.value);
      const res = await apiFetch(`/api/sites/${siteId}/events?${p}`);
      if (!res.ok) throw new Error("fetch failed");
      return res.json() as Promise<{
        timeseries: Array<{ time: string; count: number; visitors: number }>;
        properties: Array<{ dataKey: string; value: string; count: number }>;
      }>;
    },
  });

  // Referrer pages
  const referrer = useQuery({
    queryKey: ["detail", "referrer", detail?.type === "referrer" ? detail.value : "", siteId, params.toString()],
    enabled: detail?.type === "referrer",
    queryFn: async () => {
      const p = new URLSearchParams(params);
      p.set("view", "referrer-pages");
      p.set("referrer", detail!.value);
      const res = await apiFetch(`/api/sites/${siteId}/sources?${p}`);
      if (!res.ok) throw new Error("fetch failed");
      return res.json() as Promise<
        Array<{ urlPath: string; visitors: number; views: number }>
      >;
    },
  });

  // Section pages (top pages filtered by prefix)
  const section = useQuery({
    queryKey: ["detail", "section", detail?.type === "section" ? detail.value : "", siteId, params.toString()],
    enabled: detail?.type === "section",
    queryFn: async () => {
      const p = new URLSearchParams(params);
      p.append("f", `url_path:starts_with:${detail!.value}`);
      p.set("mode", "slug");
      const res = await apiFetch(`/api/sites/${siteId}/pages?${p}`);
      if (!res.ok) throw new Error("fetch failed");
      return res.json() as Promise<
        Array<{
          urlPath: string;
          views: number;
          visitors: number;
          avgTime: number;
          bounceRate: number;
          entries: number;
          exits: number;
        }>
      >;
    },
  });

  // Browser stats
  const browser = useQuery({
    queryKey: ["detail", "browser", detail?.type === "browser" ? detail.value : "", siteId, params.toString()],
    enabled: detail?.type === "browser",
    queryFn: async () => {
      const p = new URLSearchParams(params);
      p.append("f", `browser:eq:${detail!.value}`);
      const res = await apiFetch(`/api/sites/${siteId}/stats?section=pages&${p}`);
      if (!res.ok) throw new Error("fetch failed");
      return res.json() as Promise<
        Array<{ urlPath: string; views: number; visitors: number }>
      >;
    },
  });

  return { page, event, referrer, section, browser };
}

// ── Content renderers ─────────────────────────────────────────────

function PageDetail({ data }: { data: NonNullable<ReturnType<typeof useDetailData>["page"]["data"]> }) {
  return (
    <div className="space-y-6">
      {data.timeseries?.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
            Views over time
          </h4>
          <AreaChart
            data={data.timeseries}
            xKey="time"
            yKeys={["views", "visitors"]}
            labels={{ views: "Views", visitors: "Visitors" }}
            height={180}
          />
        </div>
      )}
      {data.referrers?.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
            Referrers to this page
          </h4>
          <MiniTable rows={data.referrers} labelKey="referrerDomain" valueKey="visitors" valueLabel="Visitors" />
        </div>
      )}
      {data.nextPages?.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
            Where visitors go next
          </h4>
          <MiniTable rows={data.nextPages} labelKey="urlPath" valueKey="count" valueLabel="Count" mono />
        </div>
      )}
    </div>
  );
}

function EventDetail({ data }: { data: NonNullable<ReturnType<typeof useDetailData>["event"]["data"]> }) {
  return (
    <div className="space-y-6">
      {data.timeseries?.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
            Event over time
          </h4>
          <AreaChart
            data={data.timeseries}
            xKey="time"
            yKeys={["count"]}
            labels={{ count: "Count" }}
            height={180}
          />
        </div>
      )}
      {data.properties?.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
            Properties
          </h4>
          {data.properties.map((prop, i) => (
            <StatRow key={i} label={`${prop.dataKey}: ${prop.value}`} value={prop.count} />
          ))}
        </div>
      )}
    </div>
  );
}

function ReferrerDetail({ data }: { data: NonNullable<ReturnType<typeof useDetailData>["referrer"]["data"]> }) {
  return (
    <div>
      <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
        Pages from this source
      </h4>
      <MiniTable rows={data} labelKey="urlPath" valueKey="visitors" valueLabel="Visitors" mono />
    </div>
  );
}

function SectionDetail({ data }: { data: NonNullable<ReturnType<typeof useDetailData>["section"]["data"]> }) {
  const totalViews = data.reduce((s, p) => s + p.views, 0);
  const totalVisitors = data.reduce((s, p) => s + p.visitors, 0);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-md border p-3">
          <div className="text-xs text-muted-foreground">Total views</div>
          <div className="text-lg font-semibold tabular-nums">{formatNumber(totalViews)}</div>
        </div>
        <div className="rounded-md border p-3">
          <div className="text-xs text-muted-foreground">Total visitors</div>
          <div className="text-lg font-semibold tabular-nums">{formatNumber(totalVisitors)}</div>
        </div>
      </div>
      <div>
        <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
          Pages in this section
        </h4>
        <MiniTable rows={data} labelKey="urlPath" valueKey="views" valueLabel="Views" mono />
      </div>
    </div>
  );
}

function BrowserDetail({
  data,
  name,
}: {
  data: NonNullable<ReturnType<typeof useDetailData>["browser"]["data"]>;
  name: string;
}) {
  return (
    <div>
      <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
        Top pages for {name}
      </h4>
      <MiniTable rows={data} labelKey="urlPath" valueKey="views" valueLabel="Views" mono />
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────

const TITLES: Record<DetailKind["type"], string> = {
  section: "Section",
  page: "Page",
  referrer: "Referrer",
  event: "Event",
  browser: "Browser",
};

export function DetailSheet({ detail, onClose }: Props) {
  const queries = useDetailData(detail);

  const isLoading =
    (detail?.type === "page" && queries.page.isLoading) ||
    (detail?.type === "event" && queries.event.isLoading) ||
    (detail?.type === "referrer" && queries.referrer.isLoading) ||
    (detail?.type === "section" && queries.section.isLoading) ||
    (detail?.type === "browser" && queries.browser.isLoading);

  return (
    <Dialog open={detail !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {detail ? TITLES[detail.type] : ""}
          </DialogTitle>
          <DialogDescription className="font-mono text-xs break-all">
            {detail?.value}
          </DialogDescription>
        </DialogHeader>
        <div className="pb-2">
          {isLoading ? (
            <div className="space-y-4 pt-2">
              <Skeleton className="h-[180px] w-full" />
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-full" />
            </div>
          ) : (
            <>
              {detail?.type === "page" && queries.page.data && (
                <PageDetail data={queries.page.data} />
              )}
              {detail?.type === "event" && queries.event.data && (
                <EventDetail data={queries.event.data} />
              )}
              {detail?.type === "referrer" && queries.referrer.data && (
                <ReferrerDetail data={queries.referrer.data} />
              )}
              {detail?.type === "section" && queries.section.data && (
                <SectionDetail data={queries.section.data} />
              )}
              {detail?.type === "browser" && queries.browser.data && (
                <BrowserDetail data={queries.browser.data} name={detail.value} />
              )}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
