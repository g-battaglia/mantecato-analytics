import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { Header } from "@/components/layout/Header";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Plus,
  LayoutDashboard,
  Trash2,
  BarChart3,
  Globe,
  MousePointerClick,
  TrendingUp,
  Pencil,
} from "lucide-react";
import type { Dashboard, DashboardWidget, DashboardConfig } from "@/lib/dashboard-types";
import { apiFetch } from "@/lib/api";

/* ── Templates ── */

interface DashboardTemplate {
  id: string;
  name: string;
  description: string;
  icon: React.ReactNode;
  buildWidgets: (siteId: string) => DashboardWidget[];
}

let _uid = 0;
function uid() { return `w${++_uid}`; }

const TEMPLATES: DashboardTemplate[] = [
  {
    id: "overview",
    name: "Overview",
    description: "Key metrics, traffic chart, top pages and sources",
    icon: <BarChart3 className="h-5 w-5" />,
    buildWidgets: (s) => [
      { id: uid(), type: "metric", title: "Pageviews", x: 0, y: 0, w: 3, h: 1, config: { type: "metric", metric: "pageviews", siteId: s } },
      { id: uid(), type: "metric", title: "Visitors", x: 3, y: 0, w: 3, h: 1, config: { type: "metric", metric: "visitors", siteId: s } },
      { id: uid(), type: "metric", title: "Bounce Rate", x: 6, y: 0, w: 3, h: 1, config: { type: "metric", metric: "bounceRate", siteId: s } },
      { id: uid(), type: "metric", title: "Avg Duration", x: 9, y: 0, w: 3, h: 1, config: { type: "metric", metric: "avgDuration", siteId: s } },
      { id: uid(), type: "time-series", title: "Traffic", x: 0, y: 1, w: 12, h: 3, config: { type: "time-series", metrics: ["pageviews", "visitors"], chartType: "area", siteId: s } },
      { id: uid(), type: "table", title: "Top Pages", x: 0, y: 4, w: 6, h: 4, config: { type: "table", dataSource: "pages", limit: 10, siteId: s } },
      { id: uid(), type: "table", title: "Top Referrers", x: 6, y: 4, w: 6, h: 4, config: { type: "table", dataSource: "referrers", limit: 10, siteId: s } },
    ],
  },
  {
    id: "geo",
    name: "Geographic",
    description: "World map, country breakdown, and visitor distribution",
    icon: <Globe className="h-5 w-5" />,
    buildWidgets: (s) => [
      { id: uid(), type: "metric", title: "Visitors", x: 0, y: 0, w: 4, h: 1, config: { type: "metric", metric: "visitors", siteId: s } },
      { id: uid(), type: "metric", title: "Pageviews", x: 4, y: 0, w: 4, h: 1, config: { type: "metric", metric: "pageviews", siteId: s } },
      { id: uid(), type: "metric", title: "Pages / Visit", x: 8, y: 0, w: 4, h: 1, config: { type: "metric", metric: "pagesPerVisit", siteId: s } },
      { id: uid(), type: "map", title: "Visitor Map", x: 0, y: 1, w: 8, h: 4, config: { type: "map", siteId: s } },
      { id: uid(), type: "table", title: "Countries", x: 8, y: 1, w: 4, h: 4, config: { type: "table", dataSource: "countries", limit: 15, siteId: s } },
      { id: uid(), type: "pie", title: "Devices", x: 0, y: 5, w: 4, h: 3, config: { type: "pie", dataSource: "devices", limit: 5, siteId: s } },
      { id: uid(), type: "pie", title: "Browsers", x: 4, y: 5, w: 4, h: 3, config: { type: "pie", dataSource: "browsers", limit: 5, siteId: s } },
      { id: uid(), type: "pie", title: "OS", x: 8, y: 5, w: 4, h: 3, config: { type: "pie", dataSource: "os", limit: 5, siteId: s } },
    ],
  },
  {
    id: "events",
    name: "Events & Conversions",
    description: "Event tracking, conversion metrics, and trends",
    icon: <MousePointerClick className="h-5 w-5" />,
    buildWidgets: (s) => [
      { id: uid(), type: "metric", title: "Visitors", x: 0, y: 0, w: 4, h: 1, config: { type: "metric", metric: "visitors", siteId: s } },
      { id: uid(), type: "metric", title: "Pageviews", x: 4, y: 0, w: 4, h: 1, config: { type: "metric", metric: "pageviews", siteId: s } },
      { id: uid(), type: "metric", title: "Bounce Rate", x: 8, y: 0, w: 4, h: 1, config: { type: "metric", metric: "bounceRate", siteId: s } },
      { id: uid(), type: "time-series", title: "Traffic Trend", x: 0, y: 1, w: 12, h: 3, config: { type: "time-series", metrics: ["pageviews", "visitors"], chartType: "area", siteId: s } },
      { id: uid(), type: "table", title: "Events", x: 0, y: 4, w: 6, h: 4, config: { type: "table", dataSource: "events", limit: 15, siteId: s } },
      { id: uid(), type: "bar", title: "Top Pages", x: 6, y: 4, w: 6, h: 4, config: { type: "bar", dataSource: "pages", limit: 10, siteId: s } },
    ],
  },
  {
    id: "growth",
    name: "Growth",
    description: "Retention, comparisons, and engagement trends",
    icon: <TrendingUp className="h-5 w-5" />,
    buildWidgets: (s) => [
      { id: uid(), type: "comparison", title: "Visitors", x: 0, y: 0, w: 4, h: 1, config: { type: "comparison", metric: "visitors", siteId: s } },
      { id: uid(), type: "comparison", title: "Pageviews", x: 4, y: 0, w: 4, h: 1, config: { type: "comparison", metric: "pageviews", siteId: s } },
      { id: uid(), type: "comparison", title: "Bounce Rate", x: 8, y: 0, w: 4, h: 1, config: { type: "comparison", metric: "bounceRate", siteId: s } },
      { id: uid(), type: "time-series", title: "Visitor Trend", x: 0, y: 1, w: 12, h: 3, config: { type: "time-series", metrics: ["visitors"], chartType: "area", siteId: s } },
      { id: uid(), type: "retention", title: "Retention", x: 0, y: 4, w: 8, h: 4, config: { type: "retention", period: "week", siteId: s } },
      { id: uid(), type: "table", title: "Top Sources", x: 8, y: 4, w: 4, h: 4, config: { type: "table", dataSource: "referrers", limit: 10, siteId: s } },
    ],
  },
];

/* ── Hooks ── */

function useSites() {
  return useQuery<Array<{ websiteId: string; name: string; domain: string }>>({
    queryKey: ["sites"],
    queryFn: async () => {
      const res = await apiFetch("/api/sites");
      if (!res.ok) throw new Error("Failed to fetch sites");
      return res.json();
    },
  });
}

function useDashboards() {
  return useQuery<Dashboard[]>({
    queryKey: ["dashboards"],
    queryFn: async () => {
      const res = await apiFetch("/api/dashboards");
      if (!res.ok) throw new Error("Failed");
      return res.json();
    },
  });
}

/* ── Page ── */

export function DashboardsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: dashboards, isLoading } = useDashboards();
  const { data: sites } = useSites();
  const [createOpen, setCreateOpen] = useState(false);

  const createMutation = useMutation({
    mutationFn: async (payload: { name: string; description: string; websiteId: string; config?: DashboardConfig }) => {
      const res = await apiFetch("/api/dashboards", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("Failed to create");
      return res.json() as Promise<Dashboard>;
    },
    onSuccess: (dashboard) => {
      queryClient.invalidateQueries({ queryKey: ["dashboards"] });
      setCreateOpen(false);
      navigate(`/dashboards/${dashboard.id}`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const res = await apiFetch(`/api/dashboards/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error("Failed to delete");
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dashboards"] });
    },
  });

  return (
    <>
      <Header title="Custom Dashboards" />
      <div className="flex-1 p-4 space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Create custom dashboards with configurable widgets.
          </p>
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild>
              <Button size="sm" className="gap-1.5">
                <Plus className="h-3.5 w-3.5" />
                New Dashboard
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>New Dashboard</DialogTitle>
              </DialogHeader>
              <CreateDashboardFlow
                sites={sites ?? []}
                creating={createMutation.isPending}
                onCreate={(payload) => createMutation.mutate(payload)}
              />
            </DialogContent>
          </Dialog>
        </div>

        {isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-32" />
            ))}
          </div>
        ) : !dashboards?.length ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <LayoutDashboard className="mb-3 h-8 w-8" />
              <p className="text-sm font-medium">No dashboards yet</p>
              <p className="mt-1 text-xs">
                Click &quot;New Dashboard&quot; to create your first custom dashboard.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {dashboards.map((d) => {
              const site = sites?.find((s) => s.websiteId === d.websiteId);
              return (
                <Card
                  key={d.id}
                  className="cursor-pointer transition-colors hover:bg-accent/50"
                  onClick={() => navigate(`/dashboards/${d.id}`)}
                >
                  <CardHeader className="pb-2">
                    <div className="flex items-start justify-between">
                      <div>
                        <CardTitle className="text-sm font-medium">
                          {d.name}
                        </CardTitle>
                        {d.description && (
                          <CardDescription className="text-xs mt-0.5">
                            {d.description}
                          </CardDescription>
                        )}
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (confirm("Delete this dashboard?")) {
                            deleteMutation.mutate(d.id);
                          }
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>{site?.name ?? "Unknown site"}</span>
                      <span>{d.config.widgets.length} widgets</span>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}

/* ── Create Flow ── */

type Step = "choose" | "configure";

function CreateDashboardFlow({
  sites,
  creating,
  onCreate,
}: {
  sites: Array<{ websiteId: string; name: string; domain: string }>;
  creating: boolean;
  onCreate: (payload: { name: string; description: string; websiteId: string; config?: DashboardConfig }) => void;
}) {
  const [step, setStep] = useState<Step>("choose");
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [siteId, setSiteId] = useState("");

  function handleTemplateSelect(templateId: string) {
    const tpl = TEMPLATES.find((t) => t.id === templateId);
    if (tpl) {
      setSelectedTemplate(templateId);
      setName(tpl.name);
      setStep("configure");
    }
  }

  function handleCustom() {
    setSelectedTemplate(null);
    setName("");
    setStep("configure");
  }

  function handleCreate() {
    if (!name || !siteId) return;
    const tpl = TEMPLATES.find((t) => t.id === selectedTemplate);
    const config: DashboardConfig | undefined = tpl
      ? { version: 1, columns: 12, widgets: tpl.buildWidgets(siteId), dateRange: "30d" }
      : undefined;
    onCreate({ name, description: "", websiteId: siteId, config });
  }

  if (step === "choose") {
    return (
      <div className="space-y-3 pt-1">
        <p className="text-sm text-muted-foreground">Start from a template or build your own.</p>
        <div className="grid grid-cols-2 gap-2">
          {TEMPLATES.map((tpl) => (
            <button
              key={tpl.id}
              className="flex flex-col gap-1 rounded-lg border p-3 text-left transition-colors hover:bg-accent/50 hover:border-primary/30"
              onClick={() => handleTemplateSelect(tpl.id)}
            >
              <div className="flex items-center gap-2">
                <span className="text-primary">{tpl.icon}</span>
                <span className="text-sm font-medium">{tpl.name}</span>
              </div>
              <span className="text-xs text-muted-foreground leading-snug">{tpl.description}</span>
            </button>
          ))}
        </div>
        <button
          className="flex w-full items-center gap-2 rounded-lg border border-dashed p-3 text-left transition-colors hover:bg-accent/50"
          onClick={handleCustom}
        >
          <Pencil className="h-4 w-4 text-muted-foreground" />
          <div>
            <span className="text-sm font-medium">Empty Dashboard</span>
            <span className="ml-2 text-xs text-muted-foreground">Add widgets manually</span>
          </div>
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4 pt-1">
      <div className="space-y-2">
        <Label>Name</Label>
        <Input
          placeholder="Dashboard name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoFocus
        />
      </div>
      <div className="space-y-2">
        <Label>Site</Label>
        <Select value={siteId} onValueChange={setSiteId}>
          <SelectTrigger>
            <SelectValue placeholder="Select a site" />
          </SelectTrigger>
          <SelectContent>
            {sites.map((s) => (
              <SelectItem key={s.websiteId} value={s.websiteId}>
                {s.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex gap-2">
        <Button variant="outline" className="flex-1" onClick={() => setStep("choose")}>
          Back
        </Button>
        <Button
          className="flex-1"
          disabled={!name || !siteId || creating}
          onClick={handleCreate}
        >
          {creating ? "Creating..." : selectedTemplate ? "Create from Template" : "Create Empty"}
        </Button>
      </div>
    </div>
  );
}
