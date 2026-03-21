"use client";

import { useState, useMemo } from "react";
import { type ColumnDef } from "@tanstack/react-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/data/DataTable";
import { MetricCard } from "@/components/data/MetricCard";
import { AreaChart } from "@/components/charts/AreaChart";
import { BarChart } from "@/components/charts/BarChart";
import { useSiteQuery } from "@/hooks/use-site-query";
import { format } from "date-fns";
import { ArrowLeft, MousePointerClick } from "lucide-react";

// --- Types ---

interface EventRow {
  eventName: string;
  count: number;
  visitors: number;
  lastTriggered: string | null;
}

interface EventTimeSeries {
  time: string;
  count: number;
}

interface EventProperty {
  dataKey: string;
  value: string;
  count: number;
  visitors: number;
}

interface EventDetailData {
  timeseries: EventTimeSeries[];
  properties: EventProperty[];
}

// --- Columns for event list ---

const listColumns: ColumnDef<EventRow>[] = [
  {
    accessorKey: "eventName",
    header: "Event",
    cell: ({ getValue }) => (
      <span className="font-mono text-xs">{getValue() as string}</span>
    ),
    enableSorting: false,
  },
  {
    accessorKey: "count",
    header: () => <span className="flex justify-end">Count</span>,
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
    accessorKey: "lastTriggered",
    header: () => <span className="flex justify-end">Last Triggered</span>,
    cell: ({ getValue }) => {
      const v = getValue() as string | null;
      return (
        <span className="flex justify-end tabular-nums">
          {v ? format(new Date(v), "MMM d, HH:mm") : "--"}
        </span>
      );
    },
  },
];

// --- Columns for properties breakdown ---

const propertyColumns: ColumnDef<EventProperty>[] = [
  {
    accessorKey: "dataKey",
    header: "Property",
    cell: ({ getValue }) => (
      <span className="font-mono text-xs">{getValue() as string}</span>
    ),
    enableSorting: false,
  },
  {
    accessorKey: "value",
    header: "Value",
    cell: ({ getValue }) => (
      <span className="text-xs">{getValue() as string}</span>
    ),
    enableSorting: false,
  },
  {
    accessorKey: "count",
    header: () => <span className="flex justify-end">Count</span>,
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
];

// --- Detail view component ---

function EventDetail({
  eventName,
  onBack,
}: {
  eventName: string;
  onBack: () => void;
}) {
  const extraParams = useMemo(() => ({ event: eventName }), [eventName]);
  const { data, isLoading } = useSiteQuery<EventDetailData>(
    "events",
    ["event-detail", eventName],
    extraParams
  );

  const timeseries = data?.timeseries ?? [];
  const properties = data?.properties ?? [];

  // Compute summary metrics from timeseries
  const totalCount = timeseries.reduce((sum, t) => sum + t.count, 0);
  const peakCount = timeseries.length > 0 ? Math.max(...timeseries.map((t) => t.count)) : 0;
  const avgCount =
    timeseries.length > 0
      ? Math.round(totalCount / timeseries.length)
      : 0;

  // Group properties by dataKey for the bar chart (top 5 per key)
  const propertyGroups = useMemo(() => {
    const groups: Record<string, EventProperty[]> = {};
    for (const p of properties) {
      if (!groups[p.dataKey]) groups[p.dataKey] = [];
      groups[p.dataKey].push(p);
    }
    return Object.entries(groups).map(([key, values]) => ({
      key,
      values: values.sort((a, b) => b.count - a.count).slice(0, 10),
    }));
  }, [properties]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onBack} className="h-8 px-2">
          <ArrowLeft className="mr-1 h-4 w-4" />
          Back
        </Button>
        <div className="flex items-center gap-2">
          <MousePointerClick className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-lg font-semibold font-mono">{eventName}</h2>
        </div>
      </div>

      {/* Summary metrics */}
      <div className="grid grid-cols-3 gap-3">
        <MetricCard
          label="Total Triggers"
          value={totalCount}
          loading={isLoading}
          tooltip="Total number of times this event was triggered in the selected period"
        />
        <MetricCard
          label="Peak (per interval)"
          value={peakCount}
          loading={isLoading}
          tooltip="Maximum number of triggers in a single time interval"
        />
        <MetricCard
          label="Avg (per interval)"
          value={avgCount}
          loading={isLoading}
          tooltip="Average number of triggers per time interval"
        />
      </div>

      {/* Timeseries chart */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Event Timeline</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex h-[300px] items-center justify-center text-sm text-muted-foreground">
              Loading...
            </div>
          ) : timeseries.length === 0 ? (
            <div className="flex h-[300px] items-center justify-center text-sm text-muted-foreground">
              No data for this event in the selected period
            </div>
          ) : (
            <AreaChart
              data={timeseries}
              xKey="time"
              yKeys={["count"]}
              labels={{ count: "Triggers" }}
              height={300}
            />
          )}
        </CardContent>
      </Card>

      {/* Properties breakdown per key — each key gets its own bar chart */}
      {propertyGroups.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2">
          {propertyGroups.map((group) => (
            <Card key={group.key}>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium font-mono">
                  {group.key}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <BarChart
                  data={group.values.map((v) => ({
                    name: v.value,
                    count: v.count,
                    visitors: v.visitors,
                  }))}
                  xKey="name"
                  yKeys={["count"]}
                  labels={{ count: "Count" }}
                  height={200}
                  horizontal
                />
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Full properties table */}
      {properties.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Event Properties
            </CardTitle>
          </CardHeader>
          <CardContent>
            <DataTable
              columns={propertyColumns}
              data={properties}
              loading={isLoading}
              searchColumn="dataKey"
              searchPlaceholder="Search properties..."
              emptyMessage="No event data properties found"
              exportFilename={`event-${eventName}-properties`}
            />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// --- Main page ---

export default function EventsPage() {
  const [selectedEvent, setSelectedEvent] = useState<string | null>(null);
  const { data, isLoading } = useSiteQuery<EventRow[]>("events", ["events"]);

  if (selectedEvent) {
    return (
      <EventDetail
        eventName={selectedEvent}
        onBack={() => setSelectedEvent(null)}
      />
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Events</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            columns={listColumns}
            data={data ?? []}
            loading={isLoading}
            searchColumn="eventName"
            searchPlaceholder="Search events..."
            emptyMessage="No events tracked in this period"
            onRowClick={(row) => setSelectedEvent(row.eventName)}
            exportFilename="events"
          />
        </CardContent>
      </Card>
    </div>
  );
}
