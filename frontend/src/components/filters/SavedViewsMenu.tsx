import { useState } from "react";
import { useParams } from "react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useFiltersStore } from "@/stores/filters";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Bookmark, Plus, Trash2, Check } from "lucide-react";
import type { DateRangePreset, Granularity } from "@/lib/constants";
import type { Filter } from "@/lib/types";

interface SavedViewConfig {
  preset: string;
  customStart?: string | null;
  customEnd?: string | null;
  granularity: string;
  filters: Array<{
    column: string;
    operator: string;
    value: string;
  }>;
  page?: string;
}

interface SavedView {
  id: string;
  name: string;
  description: string;
  config: SavedViewConfig;
  createdAt: string;
  updatedAt: string;
}

export function SavedViewsMenu() {
  const { siteId } = useParams() as { siteId: string };
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [showSave, setShowSave] = useState(false);
  const [newName, setNewName] = useState("");
  const [justSaved, setJustSaved] = useState(false);

  const {
    preset,
    customStart,
    customEnd,
    granularity,
    filters,
    setPreset,
    setCustomRange,
    setGranularity,
    clearFilters,
    addFilter,
  } = useFiltersStore();

  // Fetch saved views
  const { data: views = [] } = useQuery<SavedView[]>({
    queryKey: ["saved-views", siteId],
    queryFn: async () => {
      const res = await fetch(`/api/sites/${siteId}/saved-views`);
      if (!res.ok) throw new Error("Failed to fetch saved views");
      return res.json();
    },
    enabled: !!siteId,
  });

  // Create mutation
  const createMutation = useMutation({
    mutationFn: async (payload: { name: string; config: SavedViewConfig }) => {
      const res = await fetch(`/api/sites/${siteId}/saved-views`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: payload.name,
          description: "",
          config: payload.config,
        }),
      });
      if (!res.ok) throw new Error("Failed to save view");
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["saved-views", siteId] });
      setNewName("");
      setShowSave(false);
      setJustSaved(true);
      setTimeout(() => setJustSaved(false), 2000);
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: async (viewId: string) => {
      const res = await fetch(`/api/sites/${siteId}/saved-views/${viewId}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("Failed to delete view");
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["saved-views", siteId] });
    },
  });

  // Save current filters as a view
  function handleSave() {
    if (!newName.trim()) return;
    const config: SavedViewConfig = {
      preset,
      customStart,
      customEnd,
      granularity,
      filters: filters.map((f) => ({
        column: f.column,
        operator: f.operator,
        value: f.value,
      })),
    };
    createMutation.mutate({ name: newName.trim(), config });
  }

  // Apply a saved view
  function applyView(view: SavedView) {
    const cfg = view.config;
    clearFilters();

    if (cfg.preset === "custom" && cfg.customStart && cfg.customEnd) {
      setCustomRange(cfg.customStart, cfg.customEnd);
    } else {
      setPreset(cfg.preset as DateRangePreset);
    }

    if (cfg.granularity) {
      setGranularity(cfg.granularity as Granularity);
    }

    if (cfg.filters) {
      for (const f of cfg.filters) {
        addFilter(f as Filter);
      }
    }

    setOpen(false);
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
                {justSaved ? (
                  <Check className="h-3.5 w-3.5 text-green-500" />
                ) : (
                  <Bookmark className="h-3.5 w-3.5" />
                )}
                Views
                {views.length > 0 && (
                  <span className="ml-0.5 rounded-full bg-primary/10 px-1.5 text-[10px] tabular-nums text-primary">
                    {views.length}
                  </span>
                )}
              </Button>
            </PopoverTrigger>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="text-xs">
            Save and load filter presets
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <PopoverContent className="w-72 p-0" align="start">
        <div className="border-b p-3">
          <p className="text-xs font-medium text-muted-foreground">
            Saved Views
          </p>
        </div>

        {/* List of saved views */}
        <div className="max-h-[240px] overflow-y-auto">
          {views.length === 0 && !showSave && (
            <div className="px-3 py-6 text-center text-xs text-muted-foreground">
              No saved views yet.
              <br />
              Save the current filters as a view.
            </div>
          )}
          {views.map((view) => (
            <div
              key={view.id}
              className="group flex items-center justify-between gap-2 border-b px-3 py-2 last:border-b-0 hover:bg-muted/50"
            >
              <button
                className="flex-1 text-left text-xs"
                onClick={() => applyView(view)}
              >
                <span className="font-medium">{view.name}</span>
                <span className="ml-2 text-muted-foreground">
                  {view.config.filters?.length || 0} filter
                  {(view.config.filters?.length || 0) !== 1 ? "s" : ""}
                </span>
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  deleteMutation.mutate(view.id);
                }}
                className="opacity-0 transition-opacity group-hover:opacity-100"
              >
                <Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" />
              </button>
            </div>
          ))}
        </div>

        {/* Save new view form */}
        <div className="border-t p-2">
          {showSave ? (
            <div className="flex items-center gap-1.5">
              <Input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="View name..."
                className="h-7 text-xs"
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSave();
                  if (e.key === "Escape") setShowSave(false);
                }}
              />
              <Button
                size="sm"
                className="h-7 px-2 text-xs"
                onClick={handleSave}
                disabled={!newName.trim() || createMutation.isPending}
              >
                Save
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 px-2 text-xs"
                onClick={() => {
                  setShowSave(false);
                  setNewName("");
                }}
              >
                Cancel
              </Button>
            </div>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-full justify-start gap-1.5 text-xs"
              onClick={() => setShowSave(true)}
            >
              <Plus className="h-3.5 w-3.5" />
              Save current view
            </Button>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
