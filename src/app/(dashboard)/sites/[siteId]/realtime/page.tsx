"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { STALE_TIME } from "@/lib/constants";
import { format } from "date-fns";
import { Radio, Globe, Eye } from "lucide-react";

interface ActiveVisitor {
  sessionId: string;
  urlPath: string;
  country: string | null;
  city: string | null;
  browser: string | null;
  os: string | null;
  lastSeen: string;
}

interface RealtimeEvent {
  createdAt: string;
  urlPath: string;
  eventType: number;
  eventName: string | null;
  country: string | null;
  browser: string | null;
}

interface CurrentPage {
  urlPath: string;
  visitors: number;
}

interface RealtimeData {
  active: { count: number; visitors: ActiveVisitor[] };
  events: RealtimeEvent[];
  pages: CurrentPage[];
}

export default function RealtimePage() {
  const { siteId } = useParams() as { siteId: string };

  const { data } = useQuery<RealtimeData>({
    queryKey: ["realtime", siteId],
    queryFn: async () => {
      const res = await fetch(`/api/sites/${siteId}/realtime`);
      if (!res.ok) throw new Error("Failed to fetch realtime data");
      return res.json();
    },
    refetchInterval: STALE_TIME.REALTIME,
    staleTime: STALE_TIME.REALTIME,
  });

  return (
    <div className="space-y-4">
      {/* Active Visitors Count */}
      <Card>
        <CardContent className="flex items-center gap-4 p-6">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-green-500/10">
            <Radio className="h-6 w-6 text-green-500" />
          </div>
          <div>
            <p className="text-3xl font-bold tabular-nums">
              {data?.active.count ?? 0}
            </p>
            <p className="text-sm text-muted-foreground">
              active visitors right now
            </p>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Current Pages */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <Eye className="h-4 w-4" />
              Currently Viewing
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {data?.pages.map((page) => (
                <div
                  key={page.urlPath}
                  className="flex items-center justify-between py-1 text-sm"
                >
                  <span className="truncate font-mono text-xs">
                    {page.urlPath}
                  </span>
                  <Badge variant="secondary" className="ml-2">
                    {page.visitors}
                  </Badge>
                </div>
              ))}
              {(!data?.pages || data.pages.length === 0) && (
                <p className="py-4 text-center text-xs text-muted-foreground">
                  No active pages
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Active Visitors */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <Globe className="h-4 w-4" />
              Active Visitors
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {data?.active.visitors.map((v) => (
                <div
                  key={v.sessionId}
                  className="flex items-center justify-between py-1 text-sm"
                >
                  <div className="min-w-0">
                    <span className="truncate font-mono text-xs">
                      {v.urlPath}
                    </span>
                    <span className="ml-2 text-xs text-muted-foreground">
                      {[v.city, v.country].filter(Boolean).join(", ")}
                    </span>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {v.browser}
                  </span>
                </div>
              ))}
              {(!data?.active.visitors ||
                data.active.visitors.length === 0) && (
                <p className="py-4 text-center text-xs text-muted-foreground">
                  No active visitors
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Live Event Stream */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">
            Live Event Stream
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-1">
            {data?.events.map((evt, i) => (
              <div
                key={`${evt.createdAt}-${i}`}
                className="flex items-center gap-3 py-1 text-sm"
              >
                <span className="w-16 text-xs text-muted-foreground tabular-nums">
                  {format(new Date(evt.createdAt), "HH:mm:ss")}
                </span>
                <Badge
                  variant={evt.eventType === 1 ? "secondary" : "outline"}
                  className="text-[10px]"
                >
                  {evt.eventType === 1 ? "pageview" : evt.eventName ?? "event"}
                </Badge>
                <span className="truncate font-mono text-xs">
                  {evt.urlPath}
                </span>
                <span className="ml-auto text-xs text-muted-foreground">
                  {evt.country}
                </span>
              </div>
            ))}
            {(!data?.events || data.events.length === 0) && (
              <p className="py-4 text-center text-xs text-muted-foreground">
                Waiting for events...
              </p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
