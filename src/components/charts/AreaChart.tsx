"use client";

import {
  ResponsiveContainer,
  AreaChart as RechartsAreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import { format } from "date-fns";
import { formatNumber } from "@/lib/format";
import { CHART_COLORS } from "@/lib/constants";

interface AreaChartProps {
  data: Array<Record<string, unknown>>;
  xKey: string;
  yKeys: string[];
  labels?: Record<string, string>;
  height?: number;
  showGrid?: boolean;
}

function formatXAxis(value: string): string {
  try {
    const date = new Date(value);
    if (isNaN(date.getTime())) return value;
    return format(date, "MMM d");
  } catch {
    return value;
  }
}

export function AreaChart({
  data,
  xKey,
  yKeys,
  labels = {},
  height = 300,
  showGrid = true,
}: AreaChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RechartsAreaChart
        data={data}
        margin={{ top: 4, right: 4, left: 0, bottom: 0 }}
      >
        {showGrid && (
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="var(--color-border)"
            opacity={0.5}
          />
        )}
        <XAxis
          dataKey={xKey}
          tickFormatter={formatXAxis}
          tick={{ fontSize: 11, fill: "var(--color-muted-foreground)" }}
          axisLine={false}
          tickLine={false}
          tickMargin={8}
        />
        <YAxis
          tickFormatter={(v: number) => formatNumber(v)}
          tick={{ fontSize: 11, fill: "var(--color-muted-foreground)" }}
          axisLine={false}
          tickLine={false}
          tickMargin={4}
          width={48}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "var(--color-popover)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            fontSize: 12,
            color: "var(--color-popover-foreground)",
          }}
          labelFormatter={(label) => {
            try {
              return format(new Date(String(label)), "MMM d, yyyy HH:mm");
            } catch {
              return String(label);
            }
          }}
          formatter={(value, name) => [
            formatNumber(Number(value), false),
            labels[String(name)] || String(name),
          ]}
        />
        {yKeys.map((key, i) => (
          <Area
            key={key}
            type="monotone"
            dataKey={key}
            stroke={CHART_COLORS[i % CHART_COLORS.length]}
            fill={CHART_COLORS[i % CHART_COLORS.length]}
            fillOpacity={i === 0 ? 0.1 : 0.05}
            strokeWidth={2}
            dot={false}
            name={labels[key] || key}
          />
        ))}
      </RechartsAreaChart>
    </ResponsiveContainer>
  );
}
