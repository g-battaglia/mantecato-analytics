
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
  onBarClick?: (payload: Record<string, unknown>) => void;
}

function getActivePayload(data: unknown): Record<string, unknown> | null {
  const activePayload = (
    data as {
      activePayload?: Array<{ payload?: Record<string, unknown> }>;
      payload?: Record<string, unknown>;
    }
  )?.activePayload;

  if (activePayload?.[0]?.payload) {
    return activePayload[0].payload;
  }

  return (
    data as {
      payload?: Record<string, unknown>;
    }
  )?.payload ?? null;
}

function detectAxisFormat(data: Array<Record<string, unknown>>, xKey: string): string {
  if (data.length < 2) return "MMM d";
  try {
    const a = new Date(String(data[0][xKey])).getTime();
    const b = new Date(String(data[1][xKey])).getTime();
    const diffHours = Math.abs(b - a) / (1000 * 60 * 60);
    if (diffHours < 1) return "HH:mm";
    if (diffHours < 24) return "HH:mm";
    if (diffHours < 24 * 32) return "MMM d";
    return "MMM yyyy";
  } catch {
    return "MMM d";
  }
}

function makeFormatXAxis(data: Array<Record<string, unknown>>, xKey: string) {
  const fmt = detectAxisFormat(data, xKey);
  return (value: string): string => {
    try {
      const date = new Date(value);
      if (isNaN(date.getTime())) return value;
      return format(date, fmt);
    } catch {
      return value;
    }
  };
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
  onBarClick,
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
  const formatXAxis = makeFormatXAxis(data, xKey);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RechartsBarChart
        data={data}
        layout={layout}
        margin={{ top: 4, right: 4, left: 0, bottom: 0 }}
        onClick={
          onBarClick
            ? (state) => {
                const payload = getActivePayload(state);
                if (payload) {
                  onBarClick(payload);
                }
              }
            : undefined
        }
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
              tick={{ fontSize: 12, fill: "var(--color-muted-foreground)" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey={xKey}
              tick={{ fontSize: 12, fill: "var(--color-muted-foreground)" }}
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
              tick={{ fontSize: 12, fill: "var(--color-muted-foreground)" }}
              axisLine={false}
              tickLine={false}
              tickMargin={8}
            />
            <YAxis
              tickFormatter={(v: number) => formatNumber(v)}
              tick={{ fontSize: 12, fill: "var(--color-muted-foreground)" }}
              axisLine={false}
              tickLine={false}
              tickMargin={4}
              width={48}
            />
          </>
        )}
        <Tooltip
          cursor={
            onBarClick
              ? { fill: "var(--color-accent)", fillOpacity: 0.08 }
              : false
          }
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
            cursor={onBarClick ? "pointer" : undefined}
            onClick={
              onBarClick
                ? (barState) => {
                    const payload = getActivePayload(barState);
                    if (payload) {
                      onBarClick(payload);
                    }
                  }
                : undefined
            }
          />
        ))}
      </RechartsBarChart>
    </ResponsiveContainer>
  );
}
