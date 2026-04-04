import { useState, useEffect, useCallback } from "react";
import { Plus } from "lucide-react";
import { useParams } from "react-router";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  FILTER_COLUMNS,
  FILTER_OPERATORS,
  type FilterColumn,
  type FilterOperator,
} from "@/lib/constants";
import { useFiltersStore } from "@/stores/filters";
import { useDateParams } from "@/hooks/use-site-query";
import { apiFetch } from "@/lib/api";

export function AddFilterDialog() {
  const [open, setOpen] = useState(false);
  const [column, setColumn] = useState<FilterColumn | "">("");
  const [operator, setOperator] = useState<FilterOperator>("eq");
  const [value, setValue] = useState("");
  const [search, setSearch] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const { addFilter } = useFiltersStore();
  const { siteId } = useParams() as { siteId: string };
  const { params: dateParams } = useDateParams();

  const selectedCol = FILTER_COLUMNS.find((c) => c.column === column);

  // Fetch autocomplete suggestions when column or search changes
  const fetchSuggestions = useCallback(
    async (col: string, q: string) => {
      if (!col || !siteId) return;
      setLoadingSuggestions(true);
      try {
        const p = new URLSearchParams(dateParams);
        p.set("column", col);
        if (q) p.set("search", q);
        const res = await apiFetch(
          `/api/sites/${siteId}/filter-values?${p}`
        );
        if (res.ok) {
          const data = await res.json();
          setSuggestions(data);
        }
      } catch {
        // Ignore errors for suggestions
      } finally {
        setLoadingSuggestions(false);
      }
    },
    [siteId, dateParams]
  );

  // Fetch suggestions when column changes
  useEffect(() => {
    if (column && selectedCol?.type === "select") {
      fetchSuggestions(column, "");
    } else {
      setSuggestions([]);
    }
  }, [column, selectedCol?.type, fetchSuggestions]);

  // Debounced search for suggestions
  useEffect(() => {
    if (!column || !search) return;
    const timer = setTimeout(() => {
      fetchSuggestions(column, search);
    }, 300);
    return () => clearTimeout(timer);
  }, [column, search, fetchSuggestions]);

  function handleAdd() {
    if (!column || !value) return;
    addFilter({ column, operator, value });
    resetForm();
    setOpen(false);
  }

  function handleSuggestionClick(suggestion: string) {
    setValue(suggestion);
    setSearch("");
  }

  function resetForm() {
    setColumn("");
    setOperator("eq");
    setValue("");
    setSearch("");
    setSuggestions([]);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) resetForm();
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="h-8 gap-1.5 text-xs">
          <Plus className="h-3.5 w-3.5" />
          Filter
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>Add Filter</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          {/* Column */}
          <div className="grid gap-2">
            <Label className="text-xs font-medium">Column</Label>
            <Select
              value={column}
              onValueChange={(v) => {
                setColumn(v as FilterColumn);
                setValue("");
                setSearch("");
              }}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select column..." />
              </SelectTrigger>
              <SelectContent>
                <ScrollArea className="h-[240px]">
                  {FILTER_COLUMNS.map((col) => (
                    <SelectItem key={col.column} value={col.column}>
                      {col.label}
                    </SelectItem>
                  ))}
                </ScrollArea>
              </SelectContent>
            </Select>
          </div>

          {/* Operator */}
          <div className="grid gap-2">
            <Label className="text-xs font-medium">Operator</Label>
            <Select
              value={operator}
              onValueChange={(v) => setOperator(v as FilterOperator)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(FILTER_OPERATORS).map(([key, meta]) => (
                  <SelectItem key={key} value={key}>
                    {meta.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Value */}
          <div className="grid gap-2">
            <Label className="text-xs font-medium">Value</Label>
            {selectedCol?.type === "select" && suggestions.length > 0 ? (
              <Select value={value} onValueChange={setValue}>
                <SelectTrigger>
                  <SelectValue
                    placeholder={`Select ${selectedCol.label.toLowerCase()}...`}
                  />
                </SelectTrigger>
                <SelectContent>
                  <ScrollArea className="h-[200px]">
                    {suggestions.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
                      </SelectItem>
                    ))}
                  </ScrollArea>
                </SelectContent>
              </Select>
            ) : (
              <div className="space-y-1">
                <Input
                  placeholder={
                    selectedCol
                      ? `Enter ${selectedCol.label.toLowerCase()}...`
                      : "Enter value..."
                  }
                  value={value}
                  onChange={(e) => {
                    setValue(e.target.value);
                    setSearch(e.target.value);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleAdd();
                  }}
                />
                {suggestions.length > 0 && search && (
                  <div className="rounded-md border bg-popover text-popover-foreground">
                    <ScrollArea className="h-[120px]">
                      {suggestions.map((s) => (
                        <button
                          key={s}
                          type="button"
                          className="w-full px-3 py-1.5 text-left text-sm hover:bg-accent"
                          onClick={() => handleSuggestionClick(s)}
                        >
                          {s}
                        </button>
                      ))}
                    </ScrollArea>
                  </div>
                )}
              </div>
            )}
            {loadingSuggestions && (
              <p className="text-xs text-muted-foreground">Loading...</p>
            )}
          </div>

          <Button onClick={handleAdd} disabled={!column || !value}>
            Add Filter
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
