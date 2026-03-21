"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { type ColumnDef } from "@tanstack/react-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/data/DataTable";
import { useSiteQuery } from "@/hooks/use-site-query";
import { formatDuration } from "@/lib/format";
import { format, differenceInSeconds } from "date-fns";
import { ArrowLeft, Globe, Monitor, Clock, Timer } from "lucide-react";

interface SessionRow {
  sessionId: string;
  country: string | null;
  city: string | null;
  browser: string | null;
  os: string | null;
  device: string | null;
  pagesViewed: number;
  duration: number;
  startedAt: string;
}

interface SessionActivity {
  createdAt: string;
  urlPath: string;
  pageTitle: string | null;
  eventType: number;
  eventName: string | null;
  referrerDomain: string | null;
  visitId: string;
  eventData: Array<{ key: string; value: string }> | null;
}

const columns: ColumnDef<SessionRow>[] = [
  {
    accessorKey: "sessionId",
    header: "Session",
    cell: ({ getValue }) => (
      <span className="font-mono text-xs">
        {(getValue() as string).substring(0, 8)}...
      </span>
    ),
    enableSorting: false,
  },
  {
    id: "location",
    header: "Location",
    cell: ({ row }) =>
      [row.original.city, row.original.country].filter(Boolean).join(", ") ||
      "--",
    enableSorting: false,
  },
  {
    accessorKey: "browser",
    header: "Browser",
    cell: ({ getValue }) => (getValue() as string) ?? "--",
    enableSorting: false,
  },
  {
    accessorKey: "os",
    header: "OS",
    cell: ({ getValue }) => (getValue() as string) ?? "--",
    enableSorting: false,
  },
  {
    accessorKey: "device",
    header: "Device",
    cell: ({ getValue }) => (getValue() as string) ?? "--",
    enableSorting: false,
  },
  {
    accessorKey: "pagesViewed",
    header: () => <span className="flex justify-end">Pages</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toString()}
      </span>
    ),
  },
  {
    accessorKey: "duration",
    header: () => <span className="flex justify-end">Duration</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {formatDuration(getValue() as number)}
      </span>
    ),
  },
  {
    accessorKey: "startedAt",
    header: () => <span className="flex justify-end">Started</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {format(new Date(getValue() as string), "MMM d, HH:mm")}
      </span>
    ),
  },
];

function SessionDetail({
  sessionId,
  onBack,
}: {
  sessionId: string;
  onBack: () => void;
}) {
  const { siteId } = useParams() as { siteId: string };

  const { data, isLoading } = useQuery<SessionActivity[]>({
    queryKey: ["session-activity", siteId, sessionId],
    queryFn: async () => {
      const res = await fetch(
        `/api/sites/${siteId}/sessions?sessionId=${sessionId}`
      );
      if (!res.ok) throw new Error("Failed to fetch session");
      return res.json();
    },
  });

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <CardTitle className="text-sm font-medium">
            Session {sessionId.substring(0, 8)}...
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : (
          <div className="relative">
            {/* Vertical timeline line */}
            {data && data.length > 1 && (
              <div className="absolute left-[14px] top-6 bottom-6 w-px bg-border" />
            )}
            <div className="space-y-0">
              {data?.map((event, i) => {
                // Calculate time gap from previous event
                const prevEvent = i > 0 ? data[i - 1] : null;
                const gap = prevEvent
                  ? differenceInSeconds(
                      new Date(event.createdAt),
                      new Date(prevEvent.createdAt)
                    )
                  : 0;

                return (
                  <div key={`${event.createdAt}-${i}`}>
                    {/* Time gap indicator */}
                    {gap > 0 && (
                      <div className="flex items-center gap-2 py-1 pl-[9px]">
                        <div className="flex h-3 w-3 items-center justify-center">
                          <Timer className="h-2.5 w-2.5 text-muted-foreground/50" />
                        </div>
                        <span className="text-[10px] text-muted-foreground/60">
                          {formatDuration(gap)}
                        </span>
                      </div>
                    )}
                    {/* Event card */}
                    <div className="flex items-start gap-3 rounded-md border bg-card p-3 text-sm relative">
                      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted z-10">
                        {event.eventType === 1 ? (
                          <Globe className="h-3 w-3" />
                        ) : (
                          <Monitor className="h-3 w-3" />
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="truncate font-mono text-xs">
                            {event.urlPath}
                          </span>
                          {event.eventName && (
                            <Badge variant="secondary" className="text-xs">
                              {event.eventName}
                            </Badge>
                          )}
                        </div>
                        {event.pageTitle && (
                          <p className="truncate text-xs text-muted-foreground">
                            {event.pageTitle}
                          </p>
                        )}
                        {event.eventData && event.eventData.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {event.eventData.map((d, j) => (
                              <Badge
                                key={j}
                                variant="outline"
                                className="text-[10px]"
                              >
                                {d.key}: {d.value}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        {format(new Date(event.createdAt), "HH:mm:ss")}
                      </div>
                    </div>
                  </div>
                );
              })}
              {(!data || data.length === 0) && (
                <p className="py-4 text-center text-muted-foreground">
                  No activity found
                </p>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function SessionsPage() {
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const { data, isLoading } = useSiteQuery<SessionRow[]>("sessions", [
    "sessions",
  ]);

  if (selectedSession) {
    return (
      <div className="space-y-4">
        <SessionDetail
          sessionId={selectedSession}
          onBack={() => setSelectedSession(null)}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Sessions</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            columns={columns}
            data={data ?? []}
            loading={isLoading}
            emptyMessage="No sessions in this period"
            onRowClick={(row) => setSelectedSession(row.sessionId)}
            pageSize={25}
          />
        </CardContent>
      </Card>
    </div>
  );
}
