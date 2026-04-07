import { useMemo, useState } from "react";
import { type ColumnDef } from "@tanstack/react-table";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { DataTable } from "@/components/data/DataTable";
import { useSiteQuery } from "@/hooks/use-site-query";
import {
  SankeyChart,
  buildSankeyFromJourneys,
} from "@/components/charts/SankeyChart";
import { useFiltersStore } from "@/stores/filters";
import { ArrowRight } from "lucide-react";

interface JourneyPath {
  path: string[];
  count: number;
  percentage: number;
}

interface EntryPoint {
  page: string;
  count: number;
  percentage: number;
}

const columns: ColumnDef<JourneyPath>[] = [
  {
    id: "path",
    header: "Journey",
    cell: ({ row }) => (
      <div className="flex flex-wrap items-center gap-1">
        {row.original.path.map((page, i) => (
          <span key={i} className="flex items-center gap-1">
            {i > 0 && (
              <ArrowRight className="h-3 w-3 shrink-0 text-muted-foreground" />
            )}
            <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">
              {page}
            </span>
          </span>
        ))}
      </div>
    ),
    enableSorting: false,
  },
  {
    accessorKey: "count",
    header: () => <span className="flex justify-end">Visits</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toLocaleString()}
      </span>
    ),
  },
  {
    accessorKey: "percentage",
    header: () => <span className="flex justify-end">%</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toFixed(1)}%
      </span>
    ),
  },
];

function deriveEntryPoints(data: JourneyPath[] | undefined): EntryPoint[] {
  if (!data || data.length === 0) return [];
  const totals = new Map<string, number>();
  let grand = 0;
  for (const j of data) {
    const entry = j.path[0];
    totals.set(entry, (totals.get(entry) ?? 0) + j.count);
    grand += j.count;
  }
  return Array.from(totals.entries())
    .map(([page, count]) => ({
      page,
      count,
      percentage: grand > 0 ? (count / grand) * 100 : 0,
    }))
    .sort((a, b) => b.count - a.count);
}

export function JourneysPage() {
  const [pathLength, setPathLength] = useState("3");
  const [limit, setLimit] = useState("30");
  const [entryFilter, setEntryFilter] = useState<string | null>(null);
  const addFilter = useFiltersStore((s) => s.addFilter);

  const { data, isLoading } = useSiteQuery<JourneyPath[]>("journeys", [
    "journeys",
    pathLength,
    limit,
  ], {
    pathLength,
    limit,
  });

  const entryPoints = useMemo(() => deriveEntryPoints(data), [data]);

  const filteredData = useMemo(() => {
    if (!entryFilter || !data) return data;
    return data.filter((j) => j.path[0] === entryFilter);
  }, [data, entryFilter]);

  const sankeyData = useMemo(() => {
    const source = filteredData ?? data;
    if (!source || source.length === 0) return null;
    return buildSankeyFromJourneys(source, 8);
  }, [filteredData, data]);

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <Label className="text-xs whitespace-nowrap">Path length</Label>
          <Select value={pathLength} onValueChange={setPathLength}>
            <SelectTrigger className="h-7 w-[70px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="2">2</SelectItem>
              <SelectItem value="3">3</SelectItem>
              <SelectItem value="4">4</SelectItem>
              <SelectItem value="5">5</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2">
          <Label className="text-xs whitespace-nowrap">Top paths</Label>
          <Select value={limit} onValueChange={setLimit}>
            <SelectTrigger className="h-7 w-[70px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="10">10</SelectItem>
              <SelectItem value="20">20</SelectItem>
              <SelectItem value="30">30</SelectItem>
              <SelectItem value="50">50</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {entryFilter && (
          <button
            className="flex items-center gap-1 rounded-md bg-primary/10 px-2 py-1 text-xs text-primary hover:bg-primary/20 transition-colors"
            onClick={() => setEntryFilter(null)}
          >
            Entry: <span className="font-mono">{entryFilter}</span>
            <span className="ml-1">&times;</span>
          </button>
        )}
      </div>

      <Tabs defaultValue="sankey">
        <TabsList>
          <TabsTrigger value="sankey">Flow Diagram</TabsTrigger>
          <TabsTrigger value="table">Path Table</TabsTrigger>
          <TabsTrigger value="entries">Entry Points</TabsTrigger>
        </TabsList>

        <TabsContent value="sankey">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">
                User Journey Flow
              </CardTitle>
              <CardDescription className="text-xs">
                {entryFilter
                  ? `Journeys starting from ${entryFilter}`
                  : "Page-to-page navigation flow across visits"}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div
                  className="flex items-center justify-center text-sm text-muted-foreground"
                  style={{ height: 400 }}
                >
                  Loading journey data...
                </div>
              ) : sankeyData ? (
                <SankeyChart data={sankeyData} height={420} />
              ) : (
                <div
                  className="flex items-center justify-center text-sm text-muted-foreground"
                  style={{ height: 400 }}
                >
                  No journey data available
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="table">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">
                User Journeys
              </CardTitle>
              <CardDescription className="text-xs">
                {entryFilter
                  ? `Journeys starting from ${entryFilter}`
                  : "Most common page sequences within visits"}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <DataTable
                columns={columns}
                data={filteredData ?? []}
                loading={isLoading}
                emptyMessage="No journey data available"
                pageSize={15}
                exportFilename="journeys"
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="entries">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">
                Entry Points
              </CardTitle>
              <CardDescription className="text-xs">
                First page visitors land on. Click to filter journeys or set as global filter.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="space-y-2">
                  {Array.from({ length: 8 }).map((_, i) => (
                    <div key={i} className="h-6 w-full animate-pulse rounded bg-muted" />
                  ))}
                </div>
              ) : entryPoints.length > 0 ? (
                <div className="space-y-0">
                  <div className="flex items-center justify-between border-b pb-1.5 mb-1 text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
                    <span>Entry Page</span>
                    <div className="flex gap-4 text-right">
                      <span className="w-16">Visits</span>
                      <span className="w-14">%</span>
                      <span className="w-16">Action</span>
                    </div>
                  </div>
                  {entryPoints.map((ep) => (
                    <div
                      key={ep.page}
                      className="flex items-center justify-between py-1.5 text-sm rounded-sm px-1 -mx-1 hover:bg-muted/50 transition-colors group"
                    >
                      <span
                        className="truncate font-mono text-xs cursor-pointer hover:underline"
                        onClick={() => setEntryFilter(ep.page)}
                      >
                        {ep.page}
                      </span>
                      <div className="flex gap-4 text-right tabular-nums items-center">
                        <span className="w-16 font-medium">
                          {ep.count.toLocaleString()}
                        </span>
                        <span className="w-14 text-muted-foreground">
                          {ep.percentage.toFixed(1)}%
                        </span>
                        <span className="w-16">
                          <button
                            className="text-[11px] text-primary/70 hover:text-primary opacity-0 group-hover:opacity-100 transition-opacity"
                            onClick={() => addFilter({ column: "url_path", operator: "eq", value: ep.page })}
                          >
                            + Filter
                          </button>
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
                  No entry point data available
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
