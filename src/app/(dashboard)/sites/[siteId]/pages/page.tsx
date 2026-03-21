"use client";

import { type ColumnDef } from "@tanstack/react-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/data/DataTable";
import { useSiteQuery } from "@/hooks/use-site-query";
import { formatDuration, formatPercent } from "@/lib/format";

interface PageRow {
  urlPath: string;
  pageTitle: string | null;
  views: number;
  visitors: number;
  avgTimeOnPage: number | null;
  medianTimeOnPage: number | null;
  entries: number;
  exits: number;
  bounceRate: number;
}

const columns: ColumnDef<PageRow>[] = [
  {
    accessorKey: "urlPath",
    header: "Page",
    cell: ({ row }) => (
      <div className="max-w-[300px]">
        <span className="block truncate font-mono text-xs">
          {row.original.urlPath}
        </span>
        {row.original.pageTitle && (
          <span className="block truncate text-xs text-muted-foreground">
            {row.original.pageTitle}
          </span>
        )}
      </div>
    ),
    enableSorting: false,
  },
  {
    accessorKey: "views",
    header: () => <span className="flex justify-end">Views</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toLocaleString()}
      </span>
    ),
  },
  {
    accessorKey: "visitors",
    header: () => <span className="flex justify-end">Visitors</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toLocaleString()}
      </span>
    ),
  },
  {
    accessorKey: "avgTimeOnPage",
    header: () => <span className="flex justify-end">Avg Time</span>,
    cell: ({ getValue }) => {
      const v = getValue() as number | null;
      return (
        <span className="flex justify-end tabular-nums">
          {v != null ? formatDuration(v) : "--"}
        </span>
      );
    },
  },
  {
    accessorKey: "bounceRate",
    header: () => <span className="flex justify-end">Bounce Rate</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {formatPercent(getValue() as number)}
      </span>
    ),
  },
  {
    accessorKey: "entries",
    header: () => <span className="flex justify-end">Entries</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toLocaleString()}
      </span>
    ),
  },
  {
    accessorKey: "exits",
    header: () => <span className="flex justify-end">Exits</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toLocaleString()}
      </span>
    ),
  },
];

export default function PagesPage() {
  const { data, isLoading } = useSiteQuery<PageRow[]>("pages", ["pages"]);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Pages</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            columns={columns}
            data={data ?? []}
            loading={isLoading}
            searchColumn="urlPath"
            searchPlaceholder="Search pages..."
            emptyMessage="No page data for this period"
          />
        </CardContent>
      </Card>
    </div>
  );
}
