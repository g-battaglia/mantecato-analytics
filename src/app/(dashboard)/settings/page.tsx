"use client";

import { Header } from "@/components/layout/Header";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { usePreferencesStore } from "@/stores/preferences";
import { useTheme } from "@/lib/theme";
import { DATE_RANGE_PRESETS, GRANULARITY_OPTIONS } from "@/lib/constants";

const COMMON_TIMEZONES = [
  "UTC",
  "Europe/Rome",
  "Europe/London",
  "Europe/Berlin",
  "Europe/Paris",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Asia/Tokyo",
  "Asia/Shanghai",
  "Asia/Kolkata",
  "Australia/Sydney",
];

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const {
    defaultDateRange,
    defaultGranularity,
    tableRows,
    setTableRows,
    pageMode,
    setPageMode,
    currency,
    setCurrency,
    timezone,
    setTimezone,
  } = usePreferencesStore();

  // Add setters that are missing from store — we'll use the store's set directly
  const store = usePreferencesStore;

  return (
    <>
      <Header title="Settings" />
      <div className="flex-1 p-4">
        <div className="max-w-2xl space-y-4">
          {/* Appearance */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Appearance</CardTitle>
              <CardDescription>Customize the dashboard look.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <Label>Theme</Label>
                  <p className="text-xs text-muted-foreground">
                    Choose light, dark, or match your system preference
                  </p>
                </div>
                <Select
                  value={theme}
                  onValueChange={(v) =>
                    setTheme(v as "light" | "dark" | "system")
                  }
                >
                  <SelectTrigger className="w-[150px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="light">Light</SelectItem>
                    <SelectItem value="dark">Dark</SelectItem>
                    <SelectItem value="system">System</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          {/* Defaults */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Defaults</CardTitle>
              <CardDescription>
                Default values for new analytics sessions.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <Label>Default date range</Label>
                  <p className="text-xs text-muted-foreground">
                    Initial time period when opening a site
                  </p>
                </div>
                <Select
                  value={defaultDateRange}
                  onValueChange={(v) =>
                    store.setState({ defaultDateRange: v })
                  }
                >
                  <SelectTrigger className="w-[180px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(DATE_RANGE_PRESETS)
                      .filter(([key]) => key !== "custom")
                      .map(([key, preset]) => (
                        <SelectItem key={key} value={key}>
                          {preset.label}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Label>Default granularity</Label>
                  <p className="text-xs text-muted-foreground">
                    Time resolution for charts
                  </p>
                </div>
                <Select
                  value={defaultGranularity}
                  onValueChange={(v) =>
                    store.setState({ defaultGranularity: v })
                  }
                >
                  <SelectTrigger className="w-[150px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(GRANULARITY_OPTIONS).map(([key, opt]) => (
                      <SelectItem key={key} value={key}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Label>Timezone</Label>
                  <p className="text-xs text-muted-foreground">
                    Timezone for date display in charts and tables
                  </p>
                </div>
                <Select value={timezone} onValueChange={setTimezone}>
                  <SelectTrigger className="w-[200px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {COMMON_TIMEZONES.map((tz) => (
                      <SelectItem key={tz} value={tz}>
                        {tz.replace(/_/g, " ")}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          {/* Data Display */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">
                Data Display
              </CardTitle>
              <CardDescription>
                How data is shown in tables and charts.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <Label>Rows per table</Label>
                  <p className="text-xs text-muted-foreground">
                    Default number of rows shown in data tables
                  </p>
                </div>
                <Select
                  value={String(tableRows)}
                  onValueChange={(v) => setTableRows(Number(v))}
                >
                  <SelectTrigger className="w-[100px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="10">10</SelectItem>
                    <SelectItem value="25">25</SelectItem>
                    <SelectItem value="50">50</SelectItem>
                    <SelectItem value="100">100</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Label>Page grouping mode</Label>
                  <p className="text-xs text-muted-foreground">
                    How URL paths are grouped in page analytics
                  </p>
                </div>
                <Select
                  value={pageMode}
                  onValueChange={(v) => setPageMode(v as "path" | "slug")}
                >
                  <SelectTrigger className="w-[150px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="path">Full path</SelectItem>
                    <SelectItem value="slug">Slug (normalized)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Label>Currency</Label>
                  <p className="text-xs text-muted-foreground">
                    Currency for revenue metrics
                  </p>
                </div>
                <Select value={currency} onValueChange={setCurrency}>
                  <SelectTrigger className="w-[100px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="USD">USD</SelectItem>
                    <SelectItem value="EUR">EUR</SelectItem>
                    <SelectItem value="GBP">GBP</SelectItem>
                    <SelectItem value="JPY">JPY</SelectItem>
                    <SelectItem value="CAD">CAD</SelectItem>
                    <SelectItem value="AUD">AUD</SelectItem>
                    <SelectItem value="CHF">CHF</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          {/* About */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">About</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-1 text-xs text-muted-foreground">
                <p>
                  <span className="font-medium text-foreground">Mantecato</span>{" "}
                  v0.1.0
                </p>
                <p>
                  Analytics dashboard reading from the Umami database.
                  Umami collects the data; Mantecato analyzes it.
                </p>
                <p className="pt-1">
                  Built with Next.js 16, shadcn/ui, Recharts, TanStack Query
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
