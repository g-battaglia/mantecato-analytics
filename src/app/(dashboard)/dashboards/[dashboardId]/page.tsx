"use client";

import { useState, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  DragDropContext,
  Droppable,
  Draggable,
  type DropResult,
} from "@hello-pangea/dnd";
import { Header } from "@/components/layout/Header";
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
import { Plus, Trash2, GripVertical, ArrowLeft } from "lucide-react";
import { WidgetRenderer } from "@/components/dashboard/WidgetRenderer";
import { ExportMenu } from "@/components/export/ExportMenu";
import type {
  Dashboard,
  DashboardConfig,
  DashboardWidget,
  WidgetType,
  WidgetConfig,
} from "@/lib/dashboard-types";
import {
  DEFAULT_WIDGET_SIZES as SIZES,
  WIDGET_TYPE_LABELS as LABELS,
} from "@/lib/dashboard-types";

function useDashboard(id: string) {
  return useQuery<Dashboard>({
    queryKey: ["dashboard", id],
    queryFn: async () => {
      const res = await fetch(`/api/dashboards/${id}`);
      if (!res.ok) throw new Error("Not found");
      return res.json();
    },
  });
}

export default function DashboardEditorPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const dashboardId = params.dashboardId as string;
  const { data: dashboard, isLoading } = useDashboard(dashboardId);
  const [addOpen, setAddOpen] = useState(false);
  const gridRef = useRef<HTMLDivElement>(null);

  const saveMutation = useMutation({
    mutationFn: async (config: DashboardConfig) => {
      const res = await fetch(`/api/dashboards/${dashboardId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config }),
      });
      if (!res.ok) throw new Error("Failed to save");
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dashboard", dashboardId] });
    },
  });

  const addWidget = useCallback(
    (widget: DashboardWidget) => {
      if (!dashboard) return;
      const config = { ...dashboard.config };
      config.widgets = [...config.widgets, widget];
      saveMutation.mutate(config);
      setAddOpen(false);
    },
    [dashboard, saveMutation]
  );

  const removeWidget = useCallback(
    (widgetId: string) => {
      if (!dashboard) return;
      const config = { ...dashboard.config };
      config.widgets = config.widgets.filter((w) => w.id !== widgetId);
      saveMutation.mutate(config);
    },
    [dashboard, saveMutation]
  );

  const handleDragEnd = useCallback(
    (result: DropResult) => {
      if (!result.destination || !dashboard) return;
      const { source, destination } = result;
      if (source.index === destination.index) return;

      const widgets = [...dashboard.config.widgets];
      const [moved] = widgets.splice(source.index, 1);
      widgets.splice(destination.index, 0, moved);

      const config = { ...dashboard.config, widgets };
      // Optimistic update: mutate directly in the query cache
      queryClient.setQueryData<Dashboard>(["dashboard", dashboardId], {
        ...dashboard,
        config,
      });
      saveMutation.mutate(config);
    },
    [dashboard, dashboardId, queryClient, saveMutation]
  );

  if (isLoading) {
    return (
      <>
        <Header title="Loading..." />
        <div className="p-4 space-y-4">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-64 w-full" />
        </div>
      </>
    );
  }

  if (!dashboard) {
    return (
      <>
        <Header title="Dashboard not found" />
        <div className="flex-1 flex items-center justify-center p-4">
          <p className="text-sm text-muted-foreground">
            Dashboard not found or you don&apos;t have access.
          </p>
        </div>
      </>
    );
  }

  return (
    <>
      <Header title={dashboard.name} />
      <div className="flex-1 p-4 space-y-4">
        {/* Toolbar */}
        <div className="flex items-center justify-between">
          <Button
            variant="ghost"
            size="sm"
            className="gap-1.5"
            onClick={() => router.push("/dashboards")}
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back
          </Button>
          <div className="flex items-center gap-2">
            <ExportMenu
              data={[]}
              columns={[]}
              filename={dashboard.name.replace(/\s+/g, "-").toLowerCase()}
              captureRef={gridRef}
              pdfTitle={dashboard.name}
            />
            <Dialog open={addOpen} onOpenChange={setAddOpen}>
              <DialogTrigger asChild>
                <Button size="sm" className="gap-1.5">
                  <Plus className="h-3.5 w-3.5" />
                  Add Widget
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-md">
                <DialogHeader>
                  <DialogTitle>Add Widget</DialogTitle>
                </DialogHeader>
                <AddWidgetForm
                  siteId={dashboard.websiteId}
                  onAdd={addWidget}
                />
              </DialogContent>
            </Dialog>
          </div>
        </div>

        {/* Widget grid with drag-and-drop */}
        {dashboard.config.widgets.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-16 text-muted-foreground">
            <GripVertical className="mb-3 h-8 w-8" />
            <p className="text-sm font-medium">Empty dashboard</p>
            <p className="mt-1 text-xs">
              Click &quot;Add Widget&quot; to start building your dashboard.
            </p>
          </div>
        ) : (
          <DragDropContext onDragEnd={handleDragEnd}>
            <Droppable droppableId="dashboard-widgets" direction="horizontal">
              {(provided, snapshot) => (
                <div
                  ref={(el) => {
                    provided.innerRef(el);
                    (gridRef as React.MutableRefObject<HTMLDivElement | null>).current = el;
                  }}
                  {...provided.droppableProps}
                  className={`grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 ${
                    snapshot.isDraggingOver ? "ring-2 ring-primary/20 rounded-lg" : ""
                  }`}
                >
                  {dashboard.config.widgets.map((widget, index) => (
                    <Draggable
                      key={widget.id}
                      draggableId={widget.id}
                      index={index}
                    >
                      {(dragProvided, dragSnapshot) => (
                        <div
                          ref={dragProvided.innerRef}
                          {...dragProvided.draggableProps}
                          className={`relative group ${
                            dragSnapshot.isDragging
                              ? "z-50 opacity-90 shadow-xl ring-2 ring-primary rounded-lg"
                              : ""
                          }`}
                        >
                          {/* Drag handle */}
                          <div
                            {...dragProvided.dragHandleProps}
                            className="absolute top-2 left-2 z-10 h-6 w-6 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity cursor-grab active:cursor-grabbing"
                          >
                            <GripVertical className="h-3.5 w-3.5 text-muted-foreground" />
                          </div>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="absolute top-2 right-2 z-10 h-6 w-6 p-0 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
                            onClick={() => removeWidget(widget.id)}
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                          <WidgetRenderer
                            widget={widget}
                            dateRange={dashboard.config.dateRange}
                          />
                        </div>
                      )}
                    </Draggable>
                  ))}
                  {provided.placeholder}
                </div>
              )}
            </Droppable>
          </DragDropContext>
        )}
      </div>
    </>
  );
}

// --- Add Widget Form ---

function AddWidgetForm({
  siteId,
  onAdd,
}: {
  siteId: string;
  onAdd: (widget: DashboardWidget) => void;
}) {
  const [type, setType] = useState<WidgetType>("metric");
  const [title, setTitle] = useState("");

  // Config fields
  const [metric, setMetric] = useState("pageviews");
  const [dataSource, setDataSource] = useState("pages");
  const [chartMetrics, setChartMetrics] = useState("pageviews,visitors");
  const [noteContent, setNoteContent] = useState("");
  const [limit, setLimit] = useState("10");

  function handleAdd() {
    const size = SIZES[type];
    let config: WidgetConfig;

    switch (type) {
      case "metric":
        config = {
          type: "metric",
          metric: metric as "pageviews" | "visitors" | "visits" | "bounceRate" | "avgDuration" | "pagesPerVisit",
          siteId,
        };
        break;
      case "time-series":
        config = {
          type: "time-series",
          metrics: chartMetrics.split(",").map((s) => s.trim()),
          chartType: "area",
          siteId,
        };
        break;
      case "table":
        config = {
          type: "table",
          dataSource: dataSource as "pages" | "referrers" | "events" | "countries" | "browsers",
          limit: Number(limit),
          siteId,
        };
        break;
      case "pie":
        config = {
          type: "pie",
          dataSource: dataSource as "browsers" | "os" | "devices" | "countries",
          limit: Number(limit),
          siteId,
        };
        break;
      case "bar":
        config = {
          type: "bar",
          dataSource: dataSource as "pages" | "referrers" | "events" | "countries",
          limit: Number(limit),
          siteId,
        };
        break;
      case "note":
        config = {
          type: "note",
          content: noteContent,
        };
        break;
    }

    onAdd({
      id: `w-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      type,
      title: title || LABELS[type],
      x: 0,
      y: 0,
      w: size.w,
      h: size.h,
      config,
    });
  }

  return (
    <div className="space-y-4 pt-2">
      <div className="space-y-2">
        <Label>Widget Type</Label>
        <Select value={type} onValueChange={(v) => setType(v as WidgetType)}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(Object.entries(LABELS) as [WidgetType, string][]).map(
              ([key, label]) => (
                <SelectItem key={key} value={key}>
                  {label}
                </SelectItem>
              )
            )}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label>Title</Label>
        <Input
          placeholder={LABELS[type]}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>

      {/* Type-specific fields */}
      {type === "metric" && (
        <div className="space-y-2">
          <Label>Metric</Label>
          <Select value={metric} onValueChange={setMetric}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="pageviews">Pageviews</SelectItem>
              <SelectItem value="visitors">Visitors</SelectItem>
              <SelectItem value="visits">Visits</SelectItem>
              <SelectItem value="bounceRate">Bounce Rate</SelectItem>
              <SelectItem value="avgDuration">Avg Duration</SelectItem>
              <SelectItem value="pagesPerVisit">Pages / Visit</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}

      {type === "time-series" && (
        <div className="space-y-2">
          <Label>Metrics (comma-separated)</Label>
          <Input
            placeholder="pageviews,visitors"
            value={chartMetrics}
            onChange={(e) => setChartMetrics(e.target.value)}
          />
        </div>
      )}

      {(type === "table" || type === "bar") && (
        <>
          <div className="space-y-2">
            <Label>Data Source</Label>
            <Select value={dataSource} onValueChange={setDataSource}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="pages">Top Pages</SelectItem>
                <SelectItem value="referrers">Referrers</SelectItem>
                <SelectItem value="events">Events</SelectItem>
                <SelectItem value="countries">Countries</SelectItem>
                <SelectItem value="browsers">Browsers</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Limit</Label>
            <Input
              type="number"
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              min="1"
              max="100"
            />
          </div>
        </>
      )}

      {type === "pie" && (
        <>
          <div className="space-y-2">
            <Label>Data Source</Label>
            <Select value={dataSource} onValueChange={setDataSource}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="browsers">Browsers</SelectItem>
                <SelectItem value="os">Operating Systems</SelectItem>
                <SelectItem value="devices">Devices</SelectItem>
                <SelectItem value="countries">Countries</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Limit</Label>
            <Input
              type="number"
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              min="1"
              max="20"
            />
          </div>
        </>
      )}

      {type === "note" && (
        <div className="space-y-2">
          <Label>Content</Label>
          <Input
            placeholder="Write a note..."
            value={noteContent}
            onChange={(e) => setNoteContent(e.target.value)}
          />
        </div>
      )}

      <Button className="w-full" onClick={handleAdd}>
        Add Widget
      </Button>
    </div>
  );
}
