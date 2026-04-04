import { useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MetricCard } from "@/components/data/MetricCard";
import { useFiltersStore } from "@/stores/filters";
import { format } from "date-fns";
import { apiFetch } from "@/lib/api";

interface ComparisonData {
  current: {
    pageviews: number;
    visitors: number;
    visits: number;
    bounces: number;
    totaltime: number;
  };
  previous: {
    pageviews: number;
    visitors: number;
    visits: number;
    bounces: number;
    totaltime: number;
  };
  currentRange: { start: string; end: string };
  previousRange: { start: string; end: string };
}

export function ComparePage() {
  const { siteId } = useParams() as { siteId: string };
  const { preset, comparison } = useFiltersStore();
  const compareMode =
    comparison === "none" ? "previous_period" : comparison;

  const { data, isLoading } = useQuery<ComparisonData>({
    queryKey: ["compare", siteId, preset, compareMode],
    queryFn: async () => {
      const params = new URLSearchParams({
        range: preset,
        compare: compareMode,
      });
      const res = await apiFetch(`/api/sites/${siteId}/compare?${params}`);
      if (!res.ok) throw new Error("Failed to fetch comparison");
      return res.json();
    },
  });

  const c = data?.current;
  const p = data?.previous;

  const currentBounceRate =
    c && c.visits > 0 ? (c.bounces / c.visits) * 100 : null;
  const previousBounceRate =
    p && p.visits > 0 ? (p.bounces / p.visits) * 100 : null;
  const currentAvgDuration =
    c && c.visits > 0 ? c.totaltime / c.visits : null;
  const previousAvgDuration =
    p && p.visits > 0 ? p.totaltime / p.visits : null;

  return (
    <div className="space-y-4">
      {data && (
        <Card>
          <CardContent className="flex items-center gap-4 p-4 text-sm">
            <div>
              <span className="font-medium">Current:</span>{" "}
              {format(new Date(data.currentRange.start), "MMM d")} -{" "}
              {format(new Date(data.currentRange.end), "MMM d, yyyy")}
            </div>
            <div className="text-muted-foreground">vs</div>
            <div>
              <span className="font-medium">Previous:</span>{" "}
              {format(new Date(data.previousRange.start), "MMM d")} -{" "}
              {format(new Date(data.previousRange.end), "MMM d, yyyy")}
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <MetricCard
          label="Pageviews"
          value={c?.pageviews ?? null}
          previousValue={p?.pageviews}
          loading={isLoading}
        />
        <MetricCard
          label="Visitors"
          value={c?.visitors ?? null}
          previousValue={p?.visitors}
          loading={isLoading}
        />
        <MetricCard
          label="Visits"
          value={c?.visits ?? null}
          previousValue={p?.visits}
          loading={isLoading}
        />
        <MetricCard
          label="Bounce Rate"
          value={currentBounceRate}
          previousValue={previousBounceRate}
          format="percent"
          loading={isLoading}
          invertTrend
        />
        <MetricCard
          label="Avg Duration"
          value={currentAvgDuration}
          previousValue={previousAvgDuration}
          format="duration"
          loading={isLoading}
        />
      </div>
    </div>
  );
}
