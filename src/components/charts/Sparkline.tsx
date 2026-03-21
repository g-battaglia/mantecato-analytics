"use client";

import {
  ResponsiveContainer,
  AreaChart,
  Area,
} from "recharts";
import { CHART_COLORS } from "@/lib/constants";

interface SparklineProps {
  data: Array<Record<string, unknown>>;
  dataKey: string;
  height?: number;
  width?: number;
  color?: string;
  showArea?: boolean;
}

export function Sparkline({
  data,
  dataKey,
  height = 32,
  width = 100,
  color = CHART_COLORS[0],
  showArea = true,
}: SparklineProps) {
  if (!data || data.length === 0) {
    return <div style={{ width, height }} />;
  }

  return (
    <ResponsiveContainer width={width} height={height}>
      <AreaChart data={data} margin={{ top: 2, right: 0, left: 0, bottom: 2 }}>
        <Area
          type="monotone"
          dataKey={dataKey}
          stroke={color}
          fill={showArea ? color : "transparent"}
          fillOpacity={showArea ? 0.15 : 0}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
