import {
  startOfDay,
  endOfDay,
  startOfWeek,
  endOfWeek,
  startOfMonth,
  endOfMonth,
  startOfQuarter,
  endOfQuarter,
  startOfYear,
  endOfYear,
  subDays,
  subHours,
  subMonths,
  subYears,
  subWeeks,
  subQuarters,
  differenceInDays,
} from "date-fns";
import type { DateRangePreset, Granularity } from "./constants";

export interface DateRange {
  startDate: Date;
  endDate: Date;
}

/**
 * Resolve a date range preset to actual dates.
 */
export function resolveDateRange(preset: DateRangePreset): DateRange | null {
  const now = new Date();

  switch (preset) {
    case "today":
      return { startDate: startOfDay(now), endDate: now };
    case "yesterday":
      return {
        startDate: startOfDay(subDays(now, 1)),
        endDate: endOfDay(subDays(now, 1)),
      };
    case "24h":
      return { startDate: subHours(now, 24), endDate: now };
    case "7d":
      return { startDate: subDays(now, 7), endDate: now };
    case "14d":
      return { startDate: subDays(now, 14), endDate: now };
    case "30d":
      return { startDate: subDays(now, 30), endDate: now };
    case "60d":
      return { startDate: subDays(now, 60), endDate: now };
    case "90d":
      return { startDate: subDays(now, 90), endDate: now };
    case "6m":
      return { startDate: subMonths(now, 6), endDate: now };
    case "12m":
      return { startDate: subMonths(now, 12), endDate: now };
    case "this_week":
      return {
        startDate: startOfWeek(now, { weekStartsOn: 1 }),
        endDate: now,
      };
    case "last_week": {
      const lastWeekStart = startOfWeek(subWeeks(now, 1), {
        weekStartsOn: 1,
      });
      return {
        startDate: lastWeekStart,
        endDate: endOfWeek(lastWeekStart, { weekStartsOn: 1 }),
      };
    }
    case "this_month":
      return { startDate: startOfMonth(now), endDate: now };
    case "last_month": {
      const lastMonthStart = startOfMonth(subMonths(now, 1));
      return {
        startDate: lastMonthStart,
        endDate: endOfMonth(lastMonthStart),
      };
    }
    case "this_quarter":
      return { startDate: startOfQuarter(now), endDate: now };
    case "last_quarter": {
      const lastQuarterStart = startOfQuarter(subQuarters(now, 1));
      return {
        startDate: lastQuarterStart,
        endDate: endOfQuarter(lastQuarterStart),
      };
    }
    case "this_year":
      return { startDate: startOfYear(now), endDate: now };
    case "last_year": {
      const lastYearStart = startOfYear(subYears(now, 1));
      return { startDate: lastYearStart, endDate: endOfYear(lastYearStart) };
    }
    case "all":
      // Will need to query for first event
      return null;
    case "custom":
      return null;
  }
}

/**
 * Get the comparison date range for a given range.
 */
export function getComparisonRange(
  range: DateRange,
  mode: "previous_period" | "previous_year"
): DateRange {
  const days = differenceInDays(range.endDate, range.startDate);

  if (mode === "previous_year") {
    return {
      startDate: subYears(range.startDate, 1),
      endDate: subYears(range.endDate, 1),
    };
  }

  // Previous period: same duration, immediately before
  return {
    startDate: subDays(range.startDate, days + 1),
    endDate: subDays(range.startDate, 1),
  };
}

/**
 * Auto-select granularity based on date range span.
 */
export function getAutoGranularity(range: DateRange): Exclude<Granularity, "auto"> {
  const days = differenceInDays(range.endDate, range.startDate);

  if (days <= 1) return "hour";
  if (days <= 90) return "day";
  if (days <= 365) return "week";
  return "month";
}

/**
 * Resolve granularity — if 'auto', calculate from range.
 */
export function resolveGranularity(
  granularity: Granularity,
  range: DateRange
): Exclude<Granularity, "auto"> {
  if (granularity === "auto") return getAutoGranularity(range);
  return granularity as Exclude<Granularity, "auto">;
}
