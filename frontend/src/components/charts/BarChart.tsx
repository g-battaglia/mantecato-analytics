
import {
  ResponsiveContainer,
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import { format } from "date-fns";
import { formatNumber } from "@/lib/format";
import { CHART_COLORS } from "@/lib/constants";

interface BarChartProps {
  data: Array<Record<string, unknown>>;
  xKey: string;
  yKeys: string[];
  labels?: Record<string, string>;
  height?: number;
  showGrid?: boolean;
  stacked?: boolean;
  horizontal?: boolean;
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

export function BarChart({
  data,
  xKey,
  yKeys,
  labels = {},
  height = 300,
  showGrid = true,
  stacked = false,
  horizontal = false,
}: BarChartProps) {
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

  const layout = horizontal ? "vertical" : "horizontal";

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RechartsBarChart
        data={data}
        layout={layout}
        margin={{ top: 4, right: 4, left: 0, bottom: 0 }}
      >
        {showGrid && (
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="var(--color-border)"
            opacity={0.5}
          />
        )}
        {horizontal ? (
          <>
            <XAxis
              type="number"
              tickFormatter={(v: number) => formatNumber(v)}
              tick={{ fontSize: 11, fill: "var(--color-muted-foreground)" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey={xKey}
              tick={{ fontSize: 11, fill: "var(--color-muted-foreground)" }}
              axisLine={false}
              tickLine={false}
              width={100}
            />
          </>
        ) : (
          <>
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
          </>
        )}
        <Tooltip
          contentStyle={{
            backgroundColor: "var(--color-popover)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            fontSize: 12,
            color: "var(--color-popover-foreground)",
          }}
          formatter={(value, name) => [
            formatNumber(Number(value), false),
            labels[String(name)] || String(name),
          ]}
        />
        {yKeys.map((key, i) => (
          <Bar
            key={key}
            dataKey={key}
            fill={CHART_COLORS[i % CHART_COLORS.length]}
            radius={stacked ? 0 : [2, 2, 0, 0]}
            stackId={stacked ? "stack" : undefined}
            name={labels[key] || key}
          />
        ))}
      </RechartsBarChart>
    </ResponsiveContainer>
  );
}
