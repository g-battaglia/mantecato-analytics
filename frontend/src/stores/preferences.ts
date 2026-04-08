import { create } from "zustand";
import { persist } from "zustand/middleware";

type VisualStyle = "classic" | "glass";
type UrlNormalization = "off" | "smart" | "aggressive";

interface PreferencesState {
  theme: "light" | "dark" | "system";
  visualStyle: VisualStyle;
  defaultDateRange: string;
  defaultGranularity: string;
  defaultComparison: string;
  tableRows: number;
  chartType: string;
  numberFormat: string;
  currency: string;
  timezone: string;
  pageMode: "path" | "slug";
  urlNormalization: UrlNormalization;
  sidebarCollapsed: boolean;
  botFilterEnabled: boolean;

  setTheme: (theme: "light" | "dark" | "system") => void;
  setVisualStyle: (style: VisualStyle) => void;
  setTableRows: (rows: number) => void;
  setPageMode: (mode: "path" | "slug") => void;
  setUrlNormalization: (mode: UrlNormalization) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setCurrency: (currency: string) => void;
  setTimezone: (timezone: string) => void;
  setBotFilterEnabled: (enabled: boolean) => void;
}

export const usePreferencesStore = create<PreferencesState>()(
  persist(
    (set) => ({
      theme: "system",
      visualStyle: "classic",
      defaultDateRange: "24h",
      defaultGranularity: "auto",
      defaultComparison: "previous_period",
      tableRows: 10,
      chartType: "area",
      numberFormat: "compact",
      currency: "USD",
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      pageMode: "slug",
      urlNormalization: "smart",
      sidebarCollapsed: false,
      botFilterEnabled: false,

      setTheme: (theme) => set({ theme }),
      setVisualStyle: (visualStyle) => set({ visualStyle }),
      setTableRows: (tableRows) => set({ tableRows }),
      setPageMode: (pageMode) => set({ pageMode }),
      setUrlNormalization: (urlNormalization) => set({ urlNormalization }),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      setCurrency: (currency) => set({ currency }),
      setTimezone: (timezone) => set({ timezone }),
      setBotFilterEnabled: (botFilterEnabled) => set({ botFilterEnabled }),
    }),
    {
      name: "mantecato-preferences",
    }
  )
);
