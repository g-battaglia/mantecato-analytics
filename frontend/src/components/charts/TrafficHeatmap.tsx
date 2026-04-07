/**
 * Traffic heatmap: dot-grid showing pageview intensity by day-of-week × hour.
 * Matches the Umami "Traffic" card style.
 */

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
// PostgreSQL DOW: 0=Sun, 1=Mon...6=Sat → reorder to Mon-Sun
const DOW_ORDER = [1, 2, 3, 4, 5, 6, 0];

const HOURS = Array.from({ length: 24 }, (_, i) => {
  const h = i % 12 || 12;
  const ampm = i < 12 ? "am" : "pm";
  return `${h}${ampm}`;
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
  // Build lookup: key "dow-hour" → pageviews
  const lookup = new Map<string, number>();
  let max = 1;
  for (const cell of data) {
    const key = `${cell.dayOfWeek}-${cell.hour}`;
    lookup.set(key, cell.pageviews);
    if (cell.pageviews > max) max = cell.pageviews;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th className="w-14" />
            {DAYS.map((day) => (
              <th
                key={day}
                className="px-1 pb-2 text-xs font-medium text-muted-foreground text-center"
              >
                {day}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {HOURS.map((label, hour) => (
            <tr key={hour}>
              <td className="pr-2 py-0.5 text-right text-xs text-muted-foreground whitespace-nowrap">
                {label}
              </td>
              {DOW_ORDER.map((dow, di) => {
                const pv = lookup.get(`${dow}-${hour}`) ?? 0;
                const ratio = pv / max;
                const size = 4 + ratio * 16; // 4px min, 20px max
                const opacity = pv === 0 ? 0.12 : 0.25 + ratio * 0.75;
                return (
                  <td key={di} className="text-center py-0.5 px-1">
                    <div
                      className="inline-block rounded-full"
                      style={{
                        width: size,
                        height: size,
                        backgroundColor: `oklch(0.6 0.18 270 / ${opacity})`,
                      }}
                      title={`${DAYS[di]} ${label}: ${pv.toLocaleString()} pageviews`}
                    />
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
