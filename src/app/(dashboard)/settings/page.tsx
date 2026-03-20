"use client";

import { Header } from "@/components/layout/Header";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
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

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const {
    tableRows,
    setTableRows,
    pageMode,
    setPageMode,
    currency,
    setCurrency,
  } = usePreferencesStore();

  return (
    <>
      <Header title="Settings" />
      <div className="flex-1 p-4">
        <div className="max-w-2xl space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Appearance</CardTitle>
              <CardDescription>Customize the dashboard look.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <Label>Theme</Label>
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

          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Data Display</CardTitle>
              <CardDescription>How data is shown in tables and charts.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <Label>Rows per table</Label>
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
                <Label>Page grouping mode</Label>
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
                <Label>Currency</Label>
                <Select value={currency} onValueChange={setCurrency}>
                  <SelectTrigger className="w-[100px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="USD">USD</SelectItem>
                    <SelectItem value="EUR">EUR</SelectItem>
                    <SelectItem value="GBP">GBP</SelectItem>
                    <SelectItem value="JPY">JPY</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
