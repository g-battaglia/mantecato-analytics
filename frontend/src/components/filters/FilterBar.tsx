import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DateRangePicker,
  GranularitySelector,
  CompareToggle,
} from "./DateRangePicker";
import { AddFilterDialog } from "./AddFilterDialog";
import { SavedViewsMenu } from "./SavedViewsMenu";
import { AnnotationsManager } from "@/components/annotations/AnnotationsManager";
import { useFiltersStore } from "@/stores/filters";
import { useUrlState } from "@/hooks/use-url-state";
import { FILTER_COLUMNS, FILTER_OPERATORS } from "@/lib/constants";

function getFilterLabel(column: string): string {
  return FILTER_COLUMNS.find((c) => c.column === column)?.label ?? column;
}

export function FilterBar() {
  const { filters, removeFilter, clearFilters } = useFiltersStore();

  // Sync filter state ↔ URL search params
  useUrlState();

  return (
    <div data-slot="filter-bar" className="flex flex-wrap items-center gap-2 border-b px-4 py-2">
      <DateRangePicker />
      <GranularitySelector />
      <CompareToggle />
      <div className="h-4 w-px bg-border" />
      <AddFilterDialog />
      <SavedViewsMenu />
      <AnnotationsManager />

      {filters.length > 0 && (
        <>
          {filters.map((filter, i) => (
            <Badge
              key={`${filter.column}-${filter.operator}-${filter.value}-${i}`}
              variant="secondary"
              className="gap-1 text-xs"
            >
              <span className="text-muted-foreground">
                {getFilterLabel(filter.column)}
              </span>
              <span className="text-muted-foreground/70">
                {FILTER_OPERATORS[
                  filter.operator as keyof typeof FILTER_OPERATORS
                ]?.symbol ?? "="}
              </span>
              <span className="max-w-[120px] truncate">{filter.value}</span>
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
