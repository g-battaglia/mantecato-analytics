
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Header } from "@/components/layout/Header";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { usePreferencesStore } from "@/stores/preferences";
import { useTheme } from "@/lib/theme";
import { DATE_RANGE_PRESETS, GRANULARITY_OPTIONS } from "@/lib/constants";
import {
  Plus,
  Trash2,
  Clock,
  Pause,
  Play,
  CalendarClock,
  Key,
  Copy,
  Check,
  Eye,
  EyeOff,
} from "lucide-react";
import type { ScheduledExport, ScheduledExportConfig } from "@/lib/types";
import { apiFetch } from "@/lib/api";

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

const DATA_SOURCES = [
  { value: "overview", label: "Overview stats" },
  { value: "pages", label: "Pages" },
  { value: "referrers", label: "Referrers" },
  { value: "events", label: "Events" },
  { value: "sessions", label: "Sessions" },
  { value: "devices", label: "Devices" },
  { value: "geo", label: "Geography" },
] as const;

const EXPORT_FORMATS = [
  { value: "csv", label: "CSV" },
  { value: "json", label: "JSON" },
  { value: "xlsx", label: "Excel (XLSX)" },
] as const;

const SCHEDULES = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
] as const;

const WEEK_DAYS = [
  { value: 0, label: "Sunday" },
  { value: 1, label: "Monday" },
  { value: 2, label: "Tuesday" },
  { value: 3, label: "Wednesday" },
  { value: 4, label: "Thursday" },
  { value: 5, label: "Friday" },
  { value: 6, label: "Saturday" },
];

interface Website {
  websiteId: string;
  name: string;
  domain: string | null;
}

export function SettingsPage() {
  const { theme, setTheme, visualStyle, setVisualStyle } = useTheme();
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

  const store = usePreferencesStore;

  const [showCreateDialog, setShowCreateDialog] = useState(false);

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
              <div className="flex items-center justify-between">
                <div>
                  <Label>Visual style</Label>
                  <p className="text-xs text-muted-foreground">
                    Classic or glassmorphic UI
                  </p>
                </div>
                <Select
                  value={visualStyle}
                  onValueChange={(v) =>
                    setVisualStyle(v as "classic" | "glass")
                  }
                >
                  <SelectTrigger className="w-[150px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="classic">Classic</SelectItem>
                    <SelectItem value="glass">Glass</SelectItem>
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

          {/* API Keys */}
          <ApiKeysSection />

          {/* Scheduled Exports */}
          <ScheduledExportsSection
            showCreateDialog={showCreateDialog}
            setShowCreateDialog={setShowCreateDialog}
          />

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
                  Built with Vite, React, shadcn/ui, Recharts, TanStack Query
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}

// ---------- API Keys Section ----------

interface ApiKeyInfo {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  createdAt: string;
  lastUsedAt: string | null;
}

interface ApiKeyCreateResult {
  id: string;
  name: string;
  key: string;
  prefix: string;
  scopes: string[];
  createdAt: string;
}

function ApiKeysSection() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [createdKey, setCreatedKey] = useState<ApiKeyCreateResult | null>(null);
  const [copied, setCopied] = useState(false);
  const [showKey, setShowKey] = useState(false);

  const { data: keys, isLoading } = useQuery<ApiKeyInfo[]>({
    queryKey: ["api-keys"],
    queryFn: async () => {
      const res = await apiFetch("/api/api-keys");
      if (!res.ok) throw new Error("Failed to fetch API keys");
      return res.json();
    },
  });

  const createMutation = useMutation({
    mutationFn: async (name: string) => {
      const res = await apiFetch("/api/api-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (!res.ok) throw new Error("Failed to create API key");
      return res.json() as Promise<ApiKeyCreateResult>;
    },
    onSuccess: (result) => {
      setCreatedKey(result);
      setNewKeyName("");
      setShowCreate(false);
      setCopied(false);
      setShowKey(false);
      queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const res = await apiFetch("/api/api-keys", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }),
      });
      if (!res.ok) throw new Error("Failed to delete API key");
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    },
  });

  function handleCopy(key: string) {
    navigator.clipboard.writeText(key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-sm font-medium">API Keys</CardTitle>
              <CardDescription>
                Generate keys for CLI and MCP server authentication.
              </CardDescription>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowCreate(true)}
            >
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              New Key
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : !keys?.length ? (
            <div className="flex flex-col items-center justify-center py-6 text-center">
              <Key className="mb-2 h-8 w-8 text-muted-foreground/50" />
              <p className="text-sm text-muted-foreground">
                No API keys yet.
              </p>
              <p className="text-xs text-muted-foreground">
                Create a key to authenticate CLI and MCP access.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {keys.map((k) => (
                <div
                  key={k.id}
                  className="flex items-center justify-between rounded-md border px-3 py-2"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Key className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="text-sm font-medium">{k.name}</span>
                      <code className="text-xs text-muted-foreground font-mono">
                        {k.prefix}
                      </code>
                    </div>
                    <div className="flex items-center gap-3 mt-0.5 text-xs text-muted-foreground">
                      <span>
                        Created {new Date(k.createdAt).toLocaleDateString()}
                      </span>
                      {k.lastUsedAt && (
                        <span>
                          Last used{" "}
                          {new Date(k.lastUsedAt).toLocaleDateString()}
                        </span>
                      )}
                      <span>{k.scopes.join(", ")}</span>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                    onClick={() => {
                      if (confirm(`Delete API key "${k.name}"?`)) {
                        deleteMutation.mutate(k.id);
                      }
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create Key Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Create API Key</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div className="space-y-1.5">
              <Label>Name</Label>
              <Input
                placeholder="e.g. OpenCode MCP, CLI laptop"
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowCreate(false)}>
                Cancel
              </Button>
              <Button
                onClick={() => createMutation.mutate(newKeyName)}
                disabled={!newKeyName.trim() || createMutation.isPending}
              >
                {createMutation.isPending ? "Creating..." : "Create Key"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Show Created Key Dialog */}
      <Dialog
        open={!!createdKey}
        onOpenChange={() => setCreatedKey(null)}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>API Key Created</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div className="rounded-md bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 p-3">
              <p className="text-sm text-amber-800 dark:text-amber-200 font-medium">
                Copy this key now. It will not be shown again.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label>Key</Label>
              <div className="flex gap-2">
                <code className="flex-1 rounded-md border bg-muted px-3 py-2 text-xs font-mono break-all">
                  {showKey ? createdKey?.key : createdKey?.key?.replace(/./g, "*")}
                </code>
                <Button
                  size="sm"
                  variant="outline"
                  className="shrink-0"
                  onClick={() => setShowKey(!showKey)}
                >
                  {showKey ? (
                    <EyeOff className="h-3.5 w-3.5" />
                  ) : (
                    <Eye className="h-3.5 w-3.5" />
                  )}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="shrink-0"
                  onClick={() => createdKey && handleCopy(createdKey.key)}
                >
                  {copied ? (
                    <Check className="h-3.5 w-3.5 text-green-600" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )}
                </Button>
              </div>
            </div>
            <div className="space-y-2 text-xs text-muted-foreground">
              <p className="font-medium text-foreground">Usage:</p>
              <div className="space-y-1">
                <p>CLI:</p>
                <code className="block rounded bg-muted px-2 py-1 font-mono">
                  export MANTECATO_API_KEY=&quot;{createdKey?.prefix}&quot;
                </code>
                <p className="mt-2">MCP server (opencode.json / claude config):</p>
                <code className="block rounded bg-muted px-2 py-1 font-mono">
                  {`"env": { "MANTECATO_API_KEY": "${createdKey?.prefix}" }`}
                </code>
              </div>
            </div>
            <div className="flex justify-end">
              <Button onClick={() => setCreatedKey(null)}>Done</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

// ---------- Scheduled Exports Section ----------

function ScheduledExportsSection({
  showCreateDialog,
  setShowCreateDialog,
}: {
  showCreateDialog: boolean;
  setShowCreateDialog: (v: boolean) => void;
}) {
  const queryClient = useQueryClient();

  const { data: exports, isLoading } = useQuery<ScheduledExport[]>({
    queryKey: ["scheduled-exports"],
    queryFn: async () => {
      const res = await apiFetch("/api/scheduled-exports");
      if (!res.ok) throw new Error("Failed to fetch scheduled exports");
      return res.json();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (exportId: string) => {
      const res = await apiFetch(`/api/scheduled-exports/${exportId}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("Failed to delete");
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scheduled-exports"] });
    },
  });

  const toggleMutation = useMutation({
    mutationFn: async ({
      exportId,
      enabled,
    }: {
      exportId: string;
      enabled: boolean;
    }) => {
      const res = await apiFetch(`/api/scheduled-exports/${exportId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config: { enabled } }),
      });
      if (!res.ok) throw new Error("Failed to update");
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scheduled-exports"] });
    },
  });

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-sm font-medium">
              Scheduled Exports
            </CardTitle>
            <CardDescription>
              Automatically export analytics data on a recurring schedule.
            </CardDescription>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setShowCreateDialog(true)}
          >
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            New Export
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : !exports?.length ? (
          <div className="flex flex-col items-center justify-center py-6 text-center">
            <CalendarClock className="mb-2 h-8 w-8 text-muted-foreground/50" />
            <p className="text-sm text-muted-foreground">
              No scheduled exports yet.
            </p>
            <p className="text-xs text-muted-foreground">
              Create one to automatically export data on a recurring basis.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {exports.map((exp) => (
              <div
                key={exp.id}
                className="flex items-center justify-between rounded-md border px-3 py-2"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium truncate">
                      {exp.name}
                    </span>
                    <Badge
                      variant={exp.config.enabled ? "default" : "secondary"}
                      className="text-[10px] px-1.5 py-0"
                    >
                      {exp.config.enabled ? "Active" : "Paused"}
                    </Badge>
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                      {exp.config.schedule}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-3 mt-0.5 text-xs text-muted-foreground">
                    <span>
                      {DATA_SOURCES.find((d) => d.value === exp.config.dataSource)?.label ?? exp.config.dataSource}
                    </span>
                    <span>{exp.config.format.toUpperCase()}</span>
                    {exp.config.nextRunAt && (
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        Next: {new Date(exp.config.nextRunAt).toLocaleDateString()}
                      </span>
                    )}
                    {exp.config.lastRunAt && (
                      <span>
                        Last: {new Date(exp.config.lastRunAt).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1 ml-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0"
                    onClick={() =>
                      toggleMutation.mutate({
                        exportId: exp.id,
                        enabled: !exp.config.enabled,
                      })
                    }
                    title={exp.config.enabled ? "Pause" : "Resume"}
                  >
                    {exp.config.enabled ? (
                      <Pause className="h-3.5 w-3.5" />
                    ) : (
                      <Play className="h-3.5 w-3.5" />
                    )}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                    onClick={() => {
                      if (confirm(`Delete export "${exp.name}"?`)) {
                        deleteMutation.mutate(exp.id);
                      }
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>

      <CreateExportDialog
        open={showCreateDialog}
        onOpenChange={setShowCreateDialog}
      />
    </Card>
  );
}

// ---------- Create Export Dialog ----------

function CreateExportDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [websiteId, setWebsiteId] = useState("");
  const [dataSource, setDataSource] = useState<ScheduledExportConfig["dataSource"]>("overview");
  const [format, setFormat] = useState<ScheduledExportConfig["format"]>("csv");
  const [dateRange, setDateRange] = useState("7d");
  const [schedule, setSchedule] = useState<ScheduledExportConfig["schedule"]>("weekly");
  const [weekDay, setWeekDay] = useState(1);
  const [monthDay, setMonthDay] = useState(1);

  const { data: websites } = useQuery<Website[]>({
    queryKey: ["websites"],
    queryFn: async () => {
      const res = await apiFetch("/api/sites");
      if (!res.ok) throw new Error("Failed to fetch sites");
      return res.json();
    },
    staleTime: 300_000,
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      const config: ScheduledExportConfig = {
        websiteId,
        dataSource,
        format,
        dateRange,
        schedule,
        enabled: true,
        ...(schedule === "weekly" ? { weekDay } : {}),
        ...(schedule === "monthly" ? { monthDay } : {}),
      };

      const res = await apiFetch("/api/scheduled-exports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, config }),
      });
      if (!res.ok) throw new Error("Failed to create export");
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scheduled-exports"] });
      onOpenChange(false);
      resetForm();
    },
  });

  function resetForm() {
    setName("");
    setWebsiteId("");
    setDataSource("overview");
    setFormat("csv");
    setDateRange("7d");
    setSchedule("weekly");
    setWeekDay(1);
    setMonthDay(1);
  }

  const canSubmit = name.trim() && websiteId;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Create Scheduled Export</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          {/* Name */}
          <div className="space-y-1.5">
            <Label>Name</Label>
            <Input
              placeholder="e.g. Weekly traffic report"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          {/* Website */}
          <div className="space-y-1.5">
            <Label>Website</Label>
            <Select value={websiteId} onValueChange={setWebsiteId}>
              <SelectTrigger>
                <SelectValue placeholder="Select a website" />
              </SelectTrigger>
              <SelectContent>
                {websites?.map((site) => (
                  <SelectItem key={site.websiteId} value={site.websiteId}>
                    {site.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Data source */}
          <div className="space-y-1.5">
            <Label>Data source</Label>
            <Select
              value={dataSource}
              onValueChange={(v) => setDataSource(v as ScheduledExportConfig["dataSource"])}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DATA_SOURCES.map((src) => (
                  <SelectItem key={src.value} value={src.value}>
                    {src.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Format + Date Range row */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Format</Label>
              <Select
                value={format}
                onValueChange={(v) => setFormat(v as ScheduledExportConfig["format"])}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {EXPORT_FORMATS.map((f) => (
                    <SelectItem key={f.value} value={f.value}>
                      {f.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Date range</Label>
              <Select value={dateRange} onValueChange={setDateRange}>
                <SelectTrigger>
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
          </div>

          {/* Schedule */}
          <div className="space-y-1.5">
            <Label>Schedule</Label>
            <Select
              value={schedule}
              onValueChange={(v) => setSchedule(v as ScheduledExportConfig["schedule"])}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SCHEDULES.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Weekly: day of week */}
          {schedule === "weekly" && (
            <div className="space-y-1.5">
              <Label>Day of week</Label>
              <Select
                value={String(weekDay)}
                onValueChange={(v) => setWeekDay(Number(v))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {WEEK_DAYS.map((d) => (
                    <SelectItem key={d.value} value={String(d.value)}>
                      {d.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Monthly: day of month */}
          {schedule === "monthly" && (
            <div className="space-y-1.5">
              <Label>Day of month</Label>
              <Select
                value={String(monthDay)}
                onValueChange={(v) => setMonthDay(Number(v))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
                    <SelectItem key={d} value={String(d)}>
                      {d}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button
              variant="outline"
              onClick={() => {
                onOpenChange(false);
                resetForm();
              }}
            >
              Cancel
            </Button>
            <Button
              onClick={() => createMutation.mutate()}
              disabled={!canSubmit || createMutation.isPending}
            >
              {createMutation.isPending ? "Creating..." : "Create Export"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
