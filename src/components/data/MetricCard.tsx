"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatNumber, formatPercent, formatDuration } from "@/lib/format";

interface MetricCardProps {
  label: string;
  value: number | null;
  previousValue?: number | null;
  format?: "number" | "percent" | "duration";
  loading?: boolean;
  invertTrend?: boolean; // e.g., for bounce rate, lower is better
}

export function MetricCard({
  label,
  value,
  previousValue,
  format: fmt = "number",
  loading = false,
  invertTrend = false,
}: MetricCardProps) {
  if (loading) {
    return (
      <Card>
        <CardContent className="p-4">
          <Skeleton className="mb-2 h-3 w-16" />
          <Skeleton className="h-7 w-24" />
        </CardContent>
      </Card>
    );
  }

  const displayValue =
    value === null
      ? "--"
      : fmt === "duration"
        ? formatDuration(value)
        : fmt === "percent"
          ? formatPercent(value)
          : formatNumber(value);

  let changePercent: number | null = null;
  if (value !== null && previousValue !== null && previousValue !== undefined) {
    if (previousValue === 0) {
      changePercent = value > 0 ? 100 : 0;
    } else {
      changePercent = ((value - previousValue) / previousValue) * 100;
    }
  }

  const isPositive = changePercent !== null && changePercent > 0;
  const isNegative = changePercent !== null && changePercent < 0;
  const trendColor = invertTrend
    ? isPositive
      ? "text-red-500"
      : isNegative
        ? "text-green-500"
        : "text-muted-foreground"
    : isPositive
      ? "text-green-500"
      : isNegative
        ? "text-red-500"
        : "text-muted-foreground";

  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <div className="mt-1 flex items-baseline gap-2">
          <span className="text-2xl font-semibold tabular-nums tracking-tight">
            {displayValue}
          </span>
          {changePercent !== null && (
            <span
              className={cn("flex items-center gap-0.5 text-xs font-medium", trendColor)}
            >
              {isPositive ? (
                <TrendingUp className="h-3 w-3" />
              ) : isNegative ? (
                <TrendingDown className="h-3 w-3" />
              ) : (
                <Minus className="h-3 w-3" />
              )}
              {formatPercent(Math.abs(changePercent))}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
