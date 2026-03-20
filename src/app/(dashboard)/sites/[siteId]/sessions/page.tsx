"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable, type Column } from "@/components/data/DataTable";
import { useSiteQuery } from "@/hooks/use-site-query";
import { formatDuration } from "@/lib/format";
import { format } from "date-fns";
import { ArrowLeft, Globe, Monitor, Clock } from "lucide-react";

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

const columns: Column<SessionRow>[] = [
  {
    key: "sessionId",
    label: "Session",
    render: (row) => (
      <span className="font-mono text-xs">
        {row.sessionId.substring(0, 8)}...
      </span>
    ),
  },
  {
    key: "country",
    label: "Location",
    render: (row) =>
      [row.city, row.country].filter(Boolean).join(", ") || "--",
  },
  { key: "browser", label: "Browser", render: (row) => row.browser ?? "--" },
  { key: "os", label: "OS", render: (row) => row.os ?? "--" },
  { key: "device", label: "Device", render: (row) => row.device ?? "--" },
  {
    key: "pagesViewed",
    label: "Pages",
    align: "right",
    render: (row) => row.pagesViewed.toString(),
  },
  {
    key: "duration",
    label: "Duration",
    align: "right",
    render: (row) => formatDuration(row.duration),
  },
  {
    key: "startedAt",
    label: "Started",
    align: "right",
    render: (row) => format(new Date(row.startedAt), "MMM d, HH:mm"),
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
          <Button variant="ghost" size="icon-sm" onClick={onBack}>
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
          <div className="space-y-2">
            {data?.map((event, i) => (
              <div
                key={`${event.createdAt}-${i}`}
                className="flex items-start gap-3 rounded-md border p-3 text-sm"
              >
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted">
                  {event.eventType === 1 ? (
                    <Globe className="h-3 w-3" />
                  ) : (
                    <Monitor className="h-3 w-3" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
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
            ))}
            {(!data || data.length === 0) && (
              <p className="py-4 text-center text-muted-foreground">
                No activity found
              </p>
            )}
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
            rowKey={(row) => row.sessionId}
            emptyMessage="No sessions in this period"
            onRowClick={(row) => setSelectedSession(row.sessionId)}
          />
        </CardContent>
      </Card>
    </div>
  );
}
