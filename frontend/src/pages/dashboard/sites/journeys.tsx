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
import { ArrowRight } from "lucide-react";

interface JourneyPath {
  path: string[];
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

export function JourneysPage() {
  const [pathLength, setPathLength] = useState("3");
  const [limit, setLimit] = useState("30");

  const { data, isLoading } = useSiteQuery<JourneyPath[]>("journeys", [
    "journeys",
    pathLength,
    limit,
  ], {
    pathLength,
    limit,
  });

  const sankeyData = useMemo(() => {
    if (!data || data.length === 0) return null;
    return buildSankeyFromJourneys(data, 8);
  }, [data]);

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex items-center gap-4">
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
      </div>

      <Tabs defaultValue="sankey">
        <TabsList>
          <TabsTrigger value="sankey">Flow Diagram</TabsTrigger>
          <TabsTrigger value="table">Path Table</TabsTrigger>
        </TabsList>

        <TabsContent value="sankey">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">
                User Journey Flow
              </CardTitle>
              <CardDescription className="text-xs">
                Page-to-page navigation flow across visits
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
                Most common page sequences within visits
              </CardDescription>
            </CardHeader>
            <CardContent>
              <DataTable
                columns={columns}
                data={data ?? []}
                loading={isLoading}
                emptyMessage="No journey data available"
                pageSize={15}
                exportFilename="journeys"
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
