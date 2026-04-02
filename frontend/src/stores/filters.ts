import { create } from "zustand";
import type { DateRangePreset, ComparisonMode, Granularity } from "@/lib/constants";
import type { Filter } from "@/lib/types";

interface FiltersState {
  preset: DateRangePreset;
  customStart: string | null;
  customEnd: string | null;

  granularity: Granularity;

  comparison: ComparisonMode;
  comparisonCustomStart: string | null;
  comparisonCustomEnd: string | null;

  filters: Filter[];

  setPreset: (preset: DateRangePreset) => void;
  setCustomRange: (start: string, end: string) => void;
  setGranularity: (granularity: Granularity) => void;
  setComparison: (mode: ComparisonMode) => void;
  addFilter: (filter: Filter) => void;
  removeFilter: (index: number) => void;
  clearFilters: () => void;
  setFiltersFromParams: (params: URLSearchParams) => void;
}

export const useFiltersStore = create<FiltersState>((set) => ({
  preset: "30d",
  customStart: null,
  customEnd: null,
  granularity: "auto",
  comparison: "none",
  comparisonCustomStart: null,
  comparisonCustomEnd: null,
  filters: [],

  setPreset: (preset) => set({ preset, customStart: null, customEnd: null }),

  setCustomRange: (start, end) =>
    set({ preset: "custom", customStart: start, customEnd: end }),

  setGranularity: (granularity) => set({ granularity }),

  setComparison: (comparison) => set({ comparison }),

  addFilter: (filter) =>
    set((state) => ({ filters: [...state.filters, filter] })),

  removeFilter: (index) =>
    set((state) => ({
      filters: state.filters.filter((_, i) => i !== index),
    })),

  clearFilters: () => set({ filters: [] }),

  setFiltersFromParams: (params) => {
    const preset = params.get("range") as DateRangePreset | null;
    const customStart = params.get("start");
    const customEnd = params.get("end");
    const granularity = params.get("granularity") as Granularity | null;
    const comparison = params.get("compare") as ComparisonMode | null;

    set({
      ...(preset ? { preset } : {}),
      ...(customStart && customEnd ? { customStart, customEnd } : {}),
      ...(granularity ? { granularity } : {}),
      ...(comparison ? { comparison } : {}),
    });
  },
}));
