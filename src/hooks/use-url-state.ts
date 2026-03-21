"use client";

import { useEffect, useRef } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { useFiltersStore } from "@/stores/filters";
import { DATE_RANGE_PRESETS, GRANULARITY_OPTIONS } from "@/lib/constants";
import type {
  DateRangePreset,
  Granularity,
  ComparisonMode,
} from "@/lib/constants";
import type { Filter } from "@/lib/queries";

/**
 * Parse filter strings from URL: f=column:operator:value
 */
function parseFilterParams(searchParams: URLSearchParams): Filter[] {
  return searchParams.getAll("f").flatMap((f) => {
    const firstColon = f.indexOf(":");
    if (firstColon === -1) return [];
    const column = f.substring(0, firstColon);
    const rest = f.substring(firstColon + 1);
    const secondColon = rest.indexOf(":");
    if (secondColon === -1) return [];
    const operator = rest.substring(0, secondColon);
    const value = rest.substring(secondColon + 1);
    if (!column || !operator || value === undefined) return [];
    const validOps = ["eq", "neq", "contains", "starts_with"];
    if (!validOps.includes(operator)) return [];
    return [{ column, operator: operator as Filter["operator"], value }];
  });
}

/**
 * Build URL search params from current filter state.
 */
function buildSearchParams(state: {
  preset: DateRangePreset;
  customStart: string | null;
  customEnd: string | null;
  granularity: Granularity;
  comparison: ComparisonMode;
  filters: Filter[];
}): URLSearchParams {
  const params = new URLSearchParams();

  // Only add non-default values to keep URL clean
  if (state.preset !== "30d") {
    params.set("range", state.preset);
  }
  if (state.preset === "custom" && state.customStart && state.customEnd) {
    params.set("start", state.customStart);
    params.set("end", state.customEnd);
  }
  if (state.granularity !== "auto") {
    params.set("granularity", state.granularity);
  }
  if (state.comparison !== "none") {
    params.set("compare", state.comparison);
  }

  for (const filter of state.filters) {
    params.append("f", `${filter.column}:${filter.operator}:${filter.value}`);
  }

  return params;
}

/**
 * Hook that synchronizes Zustand filter state with URL search params.
 * - On mount: reads URL params and hydrates the store
 * - On store change: updates URL params (replaceState, no navigation)
 */
export function useUrlState() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const initialized = useRef(false);
  const skipNextSync = useRef(false);

  const {
    preset,
    customStart,
    customEnd,
    granularity,
    comparison,
    filters,
    setPreset,
    setCustomRange,
    setGranularity,
    setComparison,
    addFilter,
    clearFilters,
  } = useFiltersStore();

  // Hydrate store from URL on mount
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;

    const urlRange = searchParams.get("range") as DateRangePreset | null;
    const urlStart = searchParams.get("start");
    const urlEnd = searchParams.get("end");
    const urlGranularity = searchParams.get("granularity") as Granularity | null;
    const urlComparison = searchParams.get("compare") as ComparisonMode | null;
    const urlFilters = parseFilterParams(searchParams);

    let hasChanges = false;

    if (urlRange && urlRange in DATE_RANGE_PRESETS) {
      if (urlRange === "custom" && urlStart && urlEnd) {
        setCustomRange(urlStart, urlEnd);
      } else {
        setPreset(urlRange);
      }
      hasChanges = true;
    }

    if (urlGranularity && urlGranularity in GRANULARITY_OPTIONS) {
      setGranularity(urlGranularity);
      hasChanges = true;
    }

    if (urlComparison) {
      setComparison(urlComparison);
      hasChanges = true;
    }

    if (urlFilters.length > 0) {
      clearFilters();
      for (const f of urlFilters) {
        addFilter(f);
      }
      hasChanges = true;
    }

    if (hasChanges) {
      skipNextSync.current = true;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Sync store changes to URL
  useEffect(() => {
    if (!initialized.current) return;
    if (skipNextSync.current) {
      skipNextSync.current = false;
      return;
    }

    const newParams = buildSearchParams({
      preset,
      customStart,
      customEnd,
      granularity,
      comparison,
      filters,
    });

    const newSearch = newParams.toString();
    const currentSearch = searchParams.toString();

    if (newSearch !== currentSearch) {
      const url = newSearch ? `${pathname}?${newSearch}` : pathname;
      router.replace(url, { scroll: false });
    }
  }, [
    preset,
    customStart,
    customEnd,
    granularity,
    comparison,
    filters,
    pathname,
    router,
    searchParams,
  ]);
}
