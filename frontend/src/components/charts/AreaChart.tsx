
import {
  ResponsiveContainer,
  AreaChart as RechartsAreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from "recharts";
import { format } from "date-fns";
import { formatNumber } from "@/lib/format";
import { CHART_COLORS } from "@/lib/constants";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ChartRow = Record<string, any>;

export interface AnnotationMarker {
  x: string;
  label: string;
  color: string;
}

interface AreaChartProps {
  data: ChartRow[];
  xKey: string;
  yKeys: string[];
  labels?: Record<string, string>;
  height?: number;
  showGrid?: boolean;
  /**
   * Previous period comparison data. Must be the same length as `data`.
   * Each row should use the same xKey values (aligned by index) and
   * keys prefixed with "prev_" (e.g. prev_pageviews, prev_visitors).
   */
  comparisonData?: ChartRow[];
  /** Keys in comparisonData to render as dashed overlay lines */
  comparisonKeys?: string[];
  /** Annotation markers to render as vertical reference lines */
  annotations?: AnnotationMarker[];
}

/**
 * Detect granularity from data by checking the interval between the
 * first two timestamps. Returns a date-fns format string.
 */
function detectAxisFormat(data: ChartRow[], xKey: string): string {
  if (data.length < 2) return "MMM d";
  try {
    const a = new Date(data[0][xKey]).getTime();
    const b = new Date(data[1][xKey]).getTime();
    const diffMs = Math.abs(b - a);
    const diffHours = diffMs / (1000 * 60 * 60);
    if (diffHours < 1) return "HH:mm"; // minute granularity
    if (diffHours <= 24) return "HH:mm"; // hour granularity
    if (diffHours <= 24 * 7) return "MMM d"; // day granularity
    return "MMM d";
  } catch {
    return "MMM d";
  }
}

function makeFormatXAxis(data: ChartRow[], xKey: string) {
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

/**
 * Merge current and comparison data into a single array for Recharts.
 * Comparison series use keys prefixed with "prev_".
 */
function mergeData(
  data: ChartRow[],
  comparisonData: ChartRow[] | undefined,
  yKeys: string[]
): ChartRow[] {
  if (!comparisonData || comparisonData.length === 0) return data;

  return data.map((row, i) => {
    const merged = { ...row };
    const compRow = comparisonData[i];
    if (compRow) {
      for (const key of yKeys) {
        merged[`prev_${key}`] = compRow[key] ?? 0;
      }
    }
    return merged;
  });
}

export function AreaChart({
  data,
  xKey,
  yKeys,
  labels = {},
  height = 300,
  showGrid = true,
  comparisonData,
  comparisonKeys,
  annotations,
}: AreaChartProps) {
  const hasComparison =
    comparisonData && comparisonData.length > 0 && comparisonKeys && comparisonKeys.length > 0;

  const mergedData = hasComparison
    ? mergeData(data, comparisonData, comparisonKeys)
    : data;

  // Build comparison key names (prev_pageviews, etc.)
  const prevKeys = hasComparison
    ? comparisonKeys.map((k) => `prev_${k}`)
    : [];

  const formatXAxis = makeFormatXAxis(data, xKey);
  const axisFmt = detectAxisFormat(data, xKey);
  const tooltipFmt = axisFmt === "HH:mm" ? "MMM d, yyyy HH:mm" : "MMM d, yyyy";

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RechartsAreaChart
        data={mergedData}
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
              return format(new Date(String(label)), tooltipFmt);
            } catch {
              return String(label);
            }
          }}
          formatter={(value, name) => {
            const nameStr = String(name);
            const isPrev = nameStr.startsWith("prev_");
            const baseKey = isPrev ? nameStr.slice(5) : nameStr;
            const displayLabel = labels[baseKey] || baseKey;
            return [
              formatNumber(Number(value), false),
              isPrev ? `${displayLabel} (prev)` : displayLabel,
            ];
          }}
        />
        {/* Comparison areas — rendered first so they appear behind current data */}
        {prevKeys.map((key, i) => {
          const baseKey = key.slice(5); // remove "prev_"
          const colorIndex = yKeys.indexOf(baseKey);
          const color = CHART_COLORS[(colorIndex >= 0 ? colorIndex : i) % CHART_COLORS.length];
          return (
            <Area
              key={key}
              type="monotone"
              dataKey={key}
              stroke={color}
              fill="none"
              strokeWidth={1.5}
              strokeDasharray="6 4"
              strokeOpacity={0.4}
              dot={false}
              name={key}
            />
          );
        })}
        {/* Current period areas */}
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
        {/* Annotation markers */}
        {annotations?.map((ann, i) => (
          <ReferenceLine
            key={`ann-${i}`}
            x={ann.x}
            stroke={ann.color}
            strokeDasharray="4 2"
            strokeWidth={1.5}
            label={{
              value: ann.label,
              position: "top",
              fill: ann.color,
              fontSize: 10,
              fontWeight: 500,
            }}
          />
        ))}
      </RechartsAreaChart>
    </ResponsiveContainer>
  );
}
