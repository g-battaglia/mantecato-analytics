import { useState } from "react";
import { useParams } from "react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useDateParams } from "@/hooks/use-site-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Flag, Plus, Trash2 } from "lucide-react";
import { format } from "date-fns";
import { apiFetch } from "@/lib/api";

interface Annotation {
  id: string;
  title: string;
  description: string;
  date: string;
  color: string;
  createdAt: string;
}

const ANNOTATION_COLORS = [
  { value: "blue", label: "Blue", class: "bg-blue-500" },
  { value: "green", label: "Green", class: "bg-green-500" },
  { value: "red", label: "Red", class: "bg-red-500" },
  { value: "amber", label: "Amber", class: "bg-amber-500" },
  { value: "purple", label: "Purple", class: "bg-purple-500" },
];

export function useAnnotations() {
  const { siteId } = useParams() as { siteId: string };
  const { params } = useDateParams();

  return useQuery<Annotation[]>({
    queryKey: ["annotations", siteId, params.toString()],
    queryFn: async () => {
      const res = await apiFetch(`/api/sites/${siteId}/annotations?${params}`);
      if (!res.ok) throw new Error("Failed to fetch annotations");
      return res.json();
    },
    enabled: !!siteId,
  });
}

export function AnnotationsManager() {
  const { siteId } = useParams() as { siteId: string };
  const queryClient = useQueryClient();
  const { params } = useDateParams();
  const [open, setOpen] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [title, setTitle] = useState("");
  const [date, setDate] = useState(format(new Date(), "yyyy-MM-dd"));
  const [color, setColor] = useState("blue");

  const { data: annotations = [] } = useAnnotations();

  const createMutation = useMutation({
    mutationFn: async (payload: {
      title: string;
      date: string;
      color: string;
    }) => {
      const res = await apiFetch(`/api/sites/${siteId}/annotations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: payload.title,
          description: "",
          date: new Date(payload.date).toISOString(),
          color: payload.color,
        }),
      });
      if (!res.ok) throw new Error("Failed to create annotation");
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["annotations", siteId] });
      setTitle("");
      setShowAdd(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const res = await apiFetch(
        `/api/sites/${siteId}/annotations?id=${id}&${params}`,
        { method: "DELETE" }
      );
      if (!res.ok) throw new Error("Failed to delete annotation");
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["annotations", siteId] });
    },
  });

  function handleAdd() {
    if (!title.trim() || !date) return;
    createMutation.mutate({ title: title.trim(), date, color });
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <TooltipProvider delayDuration={200}>
        <Tooltip>
          <TooltipTrigger asChild>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="h-7 gap-1.5 text-xs"
              >
                <Flag className="h-3.5 w-3.5" />
                Annotations
                {annotations.length > 0 && (
                  <span className="ml-0.5 rounded-full bg-primary/10 px-1.5 text-[10px] tabular-nums text-primary">
                    {annotations.length}
                  </span>
                )}
              </Button>
            </PopoverTrigger>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="text-xs">
            Mark events on the timeline (deployments, campaigns, etc.)
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <PopoverContent className="w-80 p-0" align="start">
        <div className="border-b p-3">
          <p className="text-xs font-medium text-muted-foreground">
            Timeline Annotations
          </p>
        </div>

        <div className="max-h-[240px] overflow-y-auto">
          {annotations.length === 0 && !showAdd && (
            <div className="px-3 py-6 text-center text-xs text-muted-foreground">
              No annotations in this period.
              <br />
              Mark key events on the timeline.
            </div>
          )}
          {annotations.map((ann) => {
            const colorInfo = ANNOTATION_COLORS.find(
              (c) => c.value === ann.color
            );
            return (
              <div
                key={ann.id}
                className="group flex items-start gap-2 border-b px-3 py-2 last:border-b-0"
              >
                <span
                  className={`mt-1 h-2 w-2 shrink-0 rounded-full ${colorInfo?.class ?? "bg-blue-500"}`}
                />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium truncate">{ann.title}</p>
                  <p className="text-[10px] text-muted-foreground tabular-nums">
                    {format(new Date(ann.date), "MMM d, yyyy")}
                  </p>
                </div>
                <button
                  onClick={() => deleteMutation.mutate(ann.id)}
                  className="opacity-0 transition-opacity group-hover:opacity-100 mt-0.5"
                >
                  <Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" />
                </button>
              </div>
            );
          })}
        </div>

        <div className="border-t p-2">
          {showAdd ? (
            <div className="space-y-2">
              <Input
                autoFocus
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Annotation title..."
                className="h-7 text-xs"
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleAdd();
                  if (e.key === "Escape") setShowAdd(false);
                }}
              />
              <div className="flex items-center gap-1.5">
                <Input
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  className="h-7 flex-1 text-xs"
                />
                <Select value={color} onValueChange={setColor}>
                  <SelectTrigger className="h-7 w-[80px] text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ANNOTATION_COLORS.map((c) => (
                      <SelectItem key={c.value} value={c.value}>
                        <span className="flex items-center gap-1.5">
                          <span
                            className={`h-2 w-2 rounded-full ${c.class}`}
                          />
                          {c.label}
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex justify-end gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 px-2 text-xs"
                  onClick={() => {
                    setShowAdd(false);
                    setTitle("");
                  }}
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  className="h-7 px-2 text-xs"
                  onClick={handleAdd}
                  disabled={!title.trim() || createMutation.isPending}
                >
                  Add
                </Button>
              </div>
            </div>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-full justify-start gap-1.5 text-xs"
              onClick={() => setShowAdd(true)}
            >
              <Plus className="h-3.5 w-3.5" />
              Add annotation
            </Button>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

/**
 * Annotation markers to render on an AreaChart.
 * Returns data for Recharts ReferenceLine components.
 */
export function getAnnotationMarkers(
  annotations: Annotation[],
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  timeseriesData: Array<Record<string, any>>,
  xKey: string
) {
  if (!annotations.length || !timeseriesData.length) return [];

  return annotations
    .map((ann) => {
      const annDate = new Date(ann.date);
      // Find the closest timeseries point
      let closestIdx = 0;
      let closestDiff = Infinity;
      timeseriesData.forEach((row, i) => {
        const rowDate = new Date(row[xKey]);
        const diff = Math.abs(rowDate.getTime() - annDate.getTime());
        if (diff < closestDiff) {
          closestDiff = diff;
          closestIdx = i;
        }
      });

      const colorMap: Record<string, string> = {
        blue: "hsl(221, 83%, 53%)",
        green: "hsl(142, 71%, 45%)",
        red: "hsl(0, 84%, 60%)",
        amber: "hsl(38, 92%, 50%)",
        purple: "hsl(271, 81%, 56%)",
      };

      return {
        x: timeseriesData[closestIdx][xKey],
        label: ann.title,
        color: colorMap[ann.color] ?? colorMap.blue,
      };
    })
    .filter(Boolean);
}
