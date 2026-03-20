"use client";

import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DateRangePicker,
  GranularitySelector,
  CompareToggle,
} from "./DateRangePicker";
import { useFiltersStore } from "@/stores/filters";

export function FilterBar() {
  const { filters, removeFilter, clearFilters } = useFiltersStore();

  return (
    <div className="flex flex-wrap items-center gap-2 border-b px-4 py-2">
      <DateRangePicker />
      <GranularitySelector />
      <CompareToggle />

      {filters.length > 0 && (
        <>
          <div className="h-4 w-px bg-border" />
          {filters.map((filter, i) => (
            <Badge
              key={`${filter.column}-${i}`}
              variant="secondary"
              className="gap-1 text-xs"
            >
              <span className="text-muted-foreground">{filter.column}:</span>
              {filter.value}
              <button
                onClick={() => removeFilter(i)}
                className="ml-0.5 rounded-sm hover:bg-muted"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-xs"
            onClick={clearFilters}
          >
            Clear all
          </Button>
        </>
      )}
    </div>
  );
}
