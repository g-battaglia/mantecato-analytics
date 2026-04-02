import { useState } from "react";
import { format } from "date-fns";
import { CalendarIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { DATE_RANGE_PRESETS, type DateRangePreset } from "@/lib/constants";
import { useFiltersStore } from "@/stores/filters";
import type { DateRange as DateRangeType } from "react-day-picker";

const QUICK_PRESETS: DateRangePreset[] = [
  "1h",
  "3h",
  "6h",
  "24h",
  "today",
  "yesterday",
  "7d",
  "14d",
  "30d",
  "90d",
  "this_month",
  "last_month",
  "this_year",
  "all",
];

export function DateRangePicker() {
  const { preset, setPreset, customStart, customEnd, setCustomRange } =
    useFiltersStore();
  const [open, setOpen] = useState(false);
  const [calendarRange, setCalendarRange] = useState<DateRangeType | undefined>(
    customStart && customEnd
      ? { from: new Date(customStart), to: new Date(customEnd) }
      : undefined
  );

  function handlePresetSelect(value: string) {
    setPreset(value as DateRangePreset);
    setOpen(false);
  }

  function handleCalendarSelect(range: DateRangeType | undefined) {
    setCalendarRange(range);
    if (range?.from && range?.to) {
      setCustomRange(range.from.toISOString(), range.to.toISOString());
      setOpen(false);
    }
  }

  const displayLabel =
    preset === "custom" && customStart && customEnd
      ? `${format(new Date(customStart), "MMM d")} - ${format(new Date(customEnd), "MMM d, yyyy")}`
      : DATE_RANGE_PRESETS[preset]?.label ?? "Select range";

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-8 gap-2 text-xs">
          <CalendarIcon className="h-3.5 w-3.5" />
          {displayLabel}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <div className="flex">
          <div className="border-r p-2">
            <div className="grid gap-0.5">
              {QUICK_PRESETS.map((p) => (
                <Button
                  key={p}
                  variant={preset === p ? "secondary" : "ghost"}
                  size="sm"
                  className="h-7 justify-start text-xs"
                  onClick={() => handlePresetSelect(p)}
                >
                  {DATE_RANGE_PRESETS[p].label}
                </Button>
              ))}
            </div>
          </div>
          <div className="p-2">
            <Calendar
              mode="range"
              selected={calendarRange}
              onSelect={handleCalendarSelect}
              numberOfMonths={2}
              disabled={{ after: new Date() }}
            />
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

export function GranularitySelector() {
  const { granularity, setGranularity } = useFiltersStore();

  return (
    <Select
      value={granularity}
      onValueChange={(v) =>
        setGranularity(v as "auto" | "minute" | "hour" | "day" | "week" | "month")
      }
    >
      <SelectTrigger className="h-8 w-[100px] text-xs">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="auto">Auto</SelectItem>
        <SelectItem value="minute">Per minute</SelectItem>
        <SelectItem value="hour">Hourly</SelectItem>
        <SelectItem value="day">Daily</SelectItem>
        <SelectItem value="week">Weekly</SelectItem>
        <SelectItem value="month">Monthly</SelectItem>
      </SelectContent>
    </Select>
  );
}

export function CompareToggle() {
  const { comparison, setComparison } = useFiltersStore();

  return (
    <Select
      value={comparison}
      onValueChange={(v) =>
        setComparison(
          v as "previous_period" | "previous_year" | "custom" | "none"
        )
      }
    >
      <SelectTrigger className="h-8 w-[150px] text-xs">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="none">No comparison</SelectItem>
        <Separator className="my-1" />
        <SelectItem value="previous_period">Previous period</SelectItem>
        <SelectItem value="previous_year">Previous year</SelectItem>
      </SelectContent>
    </Select>
  );
}
