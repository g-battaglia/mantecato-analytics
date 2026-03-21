"use client";

import { type ColumnDef } from "@tanstack/react-table";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { DataTable } from "@/components/data/DataTable";
import { useSiteQuery } from "@/hooks/use-site-query";
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

export default function JourneysPage() {
  const { data, isLoading } = useSiteQuery<JourneyPath[]>("journeys", [
    "journeys",
  ]);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">User Journeys</CardTitle>
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
          />
        </CardContent>
      </Card>
    </div>
  );
}
