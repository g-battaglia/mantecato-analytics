import { useState } from "react";
import { format } from "date-fns";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useSiteQuery } from "@/hooks/use-site-query";
import { cn } from "@/lib/utils";

interface RetentionCohort {
  cohort: string;
  cohortSize: number;
  periods: number[];
}

function RetentionGrid({ data }: { data: RetentionCohort[] }) {
  if (!data || data.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No retention data available
      </p>
    );
  }

  // Find max period that has data
  const maxPeriod = Math.max(
    ...data.map((c) =>
      c.periods.reduce(
        (max, val, idx) => (val > 0 ? Math.max(max, idx) : max),
        0
      )
    )
  );
  const periodCount = Math.min(maxPeriod + 1, 13);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr>
            <th className="sticky left-0 bg-background px-2 py-1.5 text-left font-medium">
              Cohort
            </th>
            <th className="px-2 py-1.5 text-right font-medium">Users</th>
            {Array.from({ length: periodCount }).map((_, i) => (
              <th key={i} className="px-2 py-1.5 text-center font-medium">
                {i === 0 ? "W0" : `W${i}`}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((cohort) => (
            <tr key={cohort.cohort}>
              <td className="sticky left-0 bg-background px-2 py-1 font-mono">
                {format(new Date(cohort.cohort), "MMM d")}
              </td>
              <td className="px-2 py-1 text-right tabular-nums text-muted-foreground">
                {cohort.cohortSize.toLocaleString()}
              </td>
              {cohort.periods.slice(0, periodCount).map((pct, i) => {
                const intensity = Math.min(pct / 100, 1);
                return (
                  <td key={i} className="px-0.5 py-0.5 text-center">
                    <div
                      className={cn(
                        "mx-auto flex h-7 w-12 items-center justify-center rounded text-[10px] tabular-nums",
                        pct > 0
                          ? "text-foreground"
                          : "text-muted-foreground/50"
                      )}
                      style={
                        pct > 0
                          ? {
                              backgroundColor: `hsl(221 83% 53% / ${intensity * 0.4 + 0.05})`,
                            }
                          : undefined
                      }
                    >
                      {pct > 0 ? `${pct.toFixed(0)}%` : "-"}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RetentionPage() {
  const [cohortGranularity, setCohortGranularity] = useState<"week" | "month">(
    "week"
  );

  const { data, isLoading } = useSiteQuery<RetentionCohort[]>(
    "retention",
    ["retention", cohortGranularity],
    { cohortGranularity, range: "90d" }
  );

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-sm font-medium">
                Cohort Retention
              </CardTitle>
              <CardDescription className="text-xs">
                Percentage of visitors who return in subsequent periods
              </CardDescription>
            </div>
            <Select
              value={cohortGranularity}
              onValueChange={(v) =>
                setCohortGranularity(v as "week" | "month")
              }
            >
              <SelectTrigger className="h-8 w-[120px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="week">Weekly</SelectItem>
                <SelectItem value="month">Monthly</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-7 w-full" />
              ))}
            </div>
          ) : (
            <RetentionGrid data={data ?? []} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
