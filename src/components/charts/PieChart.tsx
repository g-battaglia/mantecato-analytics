"use client";

import {
  ResponsiveContainer,
  PieChart as RechartsPieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
} from "recharts";
import { CHART_COLORS } from "@/lib/constants";

interface PieChartProps {
  data: Array<{ name: string; value: number }>;
  height?: number;
  showLegend?: boolean;
  innerRadius?: number;
  outerRadius?: number;
}

export function PieChart({
  data,
  height = 280,
  showLegend = true,
  innerRadius = 0,
  outerRadius = 90,
}: PieChartProps) {
  if (!data || data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-sm text-muted-foreground"
        style={{ height }}
      >
        No data
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RechartsPieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={innerRadius}
          outerRadius={outerRadius}
          paddingAngle={2}
          dataKey="value"
          nameKey="name"
          strokeWidth={0}
        >
          {data.map((_, i) => (
            <Cell
              key={`cell-${i}`}
              fill={CHART_COLORS[i % CHART_COLORS.length]}
            />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            backgroundColor: "var(--color-popover)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            fontSize: 12,
            color: "var(--color-popover-foreground)",
          }}
          formatter={(value, name) => [
            Number(value).toLocaleString(),
            String(name),
          ]}
        />
        {showLegend && (
          <Legend
            verticalAlign="bottom"
            height={36}
            iconType="circle"
            iconSize={8}
            formatter={(value: string) => (
              <span className="text-xs text-foreground">{value}</span>
            )}
          />
        )}
      </RechartsPieChart>
    </ResponsiveContainer>
  );
}

/**
 * Donut chart variant — just a PieChart with innerRadius set.
 */
export function DonutChart(props: Omit<PieChartProps, "innerRadius">) {
  return <PieChart {...props} innerRadius={60} />;
}
