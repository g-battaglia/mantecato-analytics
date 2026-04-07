/**
 * Traffic heatmap: dot-grid showing pageview intensity by day-of-week × hour.
 */
import { useState } from "react";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DOW_ORDER = [1, 2, 3, 4, 5, 6, 0]; // PostgreSQL DOW reordered

const HOURS = Array.from({ length: 24 }, (_, i) => {
  const h = i % 12 || 12;
  return `${h}${i < 12 ? "am" : "pm"}`;
});

interface HeatmapCell {
  dayOfWeek: number;
  hour: number;
  pageviews: number;
  visitors: number;
}

interface TrafficHeatmapProps {
  data: HeatmapCell[];
}

export function TrafficHeatmap({ data }: TrafficHeatmapProps) {
  const [hover, setHover] = useState<{ dow: number; hour: number; mx: number; my: number } | null>(null);

  const lookup = new Map<string, HeatmapCell>();
  let max = 1;
  for (const cell of data) {
    lookup.set(`${cell.dayOfWeek}-${cell.hour}`, cell);
    if (cell.pageviews > max) max = cell.pageviews;
  }

  const hoverCell = hover ? lookup.get(`${hover.dow}-${hover.hour}`) : null;

  return (
    <div className="relative">
      <div className="grid" style={{ gridTemplateColumns: "60px repeat(7, 1fr)" }}>
        {/* Header row */}
        <div />
        {DAYS.map((day) => (
          <div key={day} className="text-center pb-3 text-sm font-medium text-muted-foreground">
            {day}
          </div>
        ))}

        {/* Hour rows */}
        {HOURS.map((label, hour) => (
          <div key={hour} className="contents">
            <div className="text-right pr-3 text-sm text-muted-foreground leading-[32px]">
              {label}
            </div>
            {DOW_ORDER.map((dow, di) => {
              const cell = lookup.get(`${dow}-${hour}`);
              const pv = cell?.pageviews ?? 0;
              const ratio = pv / max;
              const size = 6 + ratio * 22; // 6px min → 28px max
              const opacity = pv === 0 ? 0.08 : 0.2 + ratio * 0.8;
              return (
                <div
                  key={di}
                  className="flex items-center justify-center h-8 cursor-default"
                  onMouseMove={(e) => {
                    setHover({ dow, hour, mx: e.clientX, my: e.clientY });
                  }}
                  onMouseLeave={() => setHover(null)}
                >
                  <div
                    className="rounded-full transition-transform duration-100"
                    style={{
                      width: size,
                      height: size,
                      backgroundColor: `oklch(0.6 0.18 270 / ${opacity})`,
                      transform: hover?.dow === dow && hover?.hour === hour ? "scale(1.3)" : "scale(1)",
                    }}
                  />
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {/* Tooltip */}
      {hover && (
        <div
          className="pointer-events-none fixed z-50 rounded-lg border bg-popover px-3 py-2 text-sm shadow-md"
          style={{
            left: hover.mx,
            top: hover.my - 12,
            transform: "translate(-50%, -100%)",
          }}
        >
          <div className="font-medium">
            {DAYS[DOW_ORDER.indexOf(hover.dow)]} {HOURS[hover.hour]}
          </div>
          <div className="mt-0.5 text-xs text-muted-foreground space-y-0.5">
            <div className="flex justify-between gap-4">
              <span>Pageviews</span>
              <span className="font-medium text-foreground tabular-nums">
                {(hoverCell?.pageviews ?? 0).toLocaleString()}
              </span>
            </div>
            <div className="flex justify-between gap-4">
              <span>Visitors</span>
              <span className="font-medium text-foreground tabular-nums">
                {(hoverCell?.visitors ?? 0).toLocaleString()}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
