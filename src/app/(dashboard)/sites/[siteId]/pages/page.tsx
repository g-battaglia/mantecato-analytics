"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable, type Column } from "@/components/data/DataTable";
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

const columns: Column<PageRow>[] = [
  {
    key: "urlPath",
    label: "Page",
    render: (row) => (
      <div className="max-w-[300px]">
        <span className="block truncate font-mono text-xs">{row.urlPath}</span>
        {row.pageTitle && (
          <span className="block truncate text-xs text-muted-foreground">
            {row.pageTitle}
          </span>
        )}
      </div>
    ),
  },
  {
    key: "views",
    label: "Views",
    align: "right",
    render: (row) => row.views.toLocaleString(),
  },
  {
    key: "visitors",
    label: "Visitors",
    align: "right",
    render: (row) => row.visitors.toLocaleString(),
  },
  {
    key: "avgTimeOnPage",
    label: "Avg Time",
    align: "right",
    render: (row) =>
      row.avgTimeOnPage != null ? formatDuration(row.avgTimeOnPage) : "--",
  },
  {
    key: "bounceRate",
    label: "Bounce Rate",
    align: "right",
    render: (row) => formatPercent(row.bounceRate),
  },
  {
    key: "entries",
    label: "Entries",
    align: "right",
    render: (row) => row.entries.toLocaleString(),
  },
  {
    key: "exits",
    label: "Exits",
    align: "right",
    render: (row) => row.exits.toLocaleString(),
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
            rowKey={(row) => row.urlPath}
            emptyMessage="No page data for this period"
          />
        </CardContent>
      </Card>
    </div>
  );
}
