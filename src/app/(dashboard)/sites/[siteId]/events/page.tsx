"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable, type Column } from "@/components/data/DataTable";
import { useSiteQuery } from "@/hooks/use-site-query";
import { format } from "date-fns";

interface EventRow {
  eventName: string;
  count: number;
  visitors: number;
  lastTriggered: string | null;
}

const columns: Column<EventRow>[] = [
  {
    key: "eventName",
    label: "Event",
    render: (row) => (
      <span className="font-mono text-xs">{row.eventName}</span>
    ),
  },
  {
    key: "count",
    label: "Count",
    align: "right",
    render: (row) => row.count.toLocaleString(),
  },
  {
    key: "visitors",
    label: "Visitors",
    align: "right",
    render: (row) => row.visitors.toLocaleString(),
  },
  {
    key: "lastTriggered",
    label: "Last Triggered",
    align: "right",
    render: (row) =>
      row.lastTriggered
        ? format(new Date(row.lastTriggered), "MMM d, HH:mm")
        : "--",
  },
];

export default function EventsPage() {
  const { data, isLoading } = useSiteQuery<EventRow[]>("events", ["events"]);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Events</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            columns={columns}
            data={data ?? []}
            loading={isLoading}
            rowKey={(row) => row.eventName}
            emptyMessage="No events tracked in this period"
          />
        </CardContent>
      </Card>
    </div>
  );
}
