import { create } from "zustand";
import { persist } from "zustand/middleware";

interface PreferencesState {
  theme: "light" | "dark" | "system";
  defaultDateRange: string;
  defaultGranularity: string;
  defaultComparison: string;
  tableRows: number;
  chartType: string;
  numberFormat: string;
  currency: string;
  timezone: string;
  pageMode: "path" | "slug";
  sidebarCollapsed: boolean;

  setTheme: (theme: "light" | "dark" | "system") => void;
  setTableRows: (rows: number) => void;
  setPageMode: (mode: "path" | "slug") => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setCurrency: (currency: string) => void;
  setTimezone: (timezone: string) => void;
}

export const usePreferencesStore = create<PreferencesState>()(
  persist(
    (set) => ({
      theme: "system",
      defaultDateRange: "24h",
      defaultGranularity: "auto",
      defaultComparison: "previous_period",
      tableRows: 10,
      chartType: "area",
      numberFormat: "compact",
      currency: "USD",
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      pageMode: "slug",
      sidebarCollapsed: false,

      setTheme: (theme) => set({ theme }),
      setTableRows: (tableRows) => set({ tableRows }),
      setPageMode: (pageMode) => set({ pageMode }),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      setCurrency: (currency) => set({ currency }),
      setTimezone: (timezone) => set({ timezone }),
    }),
    {
      name: "mantecato-preferences",
    }
  )
);
