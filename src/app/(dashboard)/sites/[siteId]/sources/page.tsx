"use client";

import { useState } from "react";
import { type ColumnDef } from "@tanstack/react-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable } from "@/components/data/DataTable";
import { useSiteQuery } from "@/hooks/use-site-query";
import { formatDuration, formatPercent } from "@/lib/format";

interface ReferrerRow {
  referrerDomain: string;
  visitors: number;
  pageviews: number;
  bounceRate: number;
  avgDuration: number;
}

interface UTMRow {
  utmSource: string | null;
  utmMedium: string | null;
  utmCampaign: string | null;
  visitors: number;
  pageviews: number;
}

const referrerColumns: ColumnDef<ReferrerRow>[] = [
  { accessorKey: "referrerDomain", header: "Source", enableSorting: false },
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
    accessorKey: "pageviews",
    header: () => <span className="flex justify-end">Pageviews</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toLocaleString()}
      </span>
    ),
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
    accessorKey: "avgDuration",
    header: () => <span className="flex justify-end">Avg Duration</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {formatDuration(getValue() as number)}
      </span>
    ),
  },
];

const utmColumns: ColumnDef<UTMRow>[] = [
  {
    accessorKey: "utmSource",
    header: "Source",
    cell: ({ getValue }) => (getValue() as string) ?? "--",
    enableSorting: false,
  },
  {
    accessorKey: "utmMedium",
    header: "Medium",
    cell: ({ getValue }) => (getValue() as string) ?? "--",
    enableSorting: false,
  },
  {
    accessorKey: "utmCampaign",
    header: "Campaign",
    cell: ({ getValue }) => (getValue() as string) ?? "--",
    enableSorting: false,
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
    accessorKey: "pageviews",
    header: () => <span className="flex justify-end">Pageviews</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toLocaleString()}
      </span>
    ),
  },
];

export default function SourcesPage() {
  const [tab, setTab] = useState("referrers");

  const { data: referrers, isLoading: refLoading } =
    useSiteQuery<ReferrerRow[]>("sources", ["sources-referrers"], {
      view: "referrers",
    });

  const { data: utm, isLoading: utmLoading } = useSiteQuery<UTMRow[]>(
    "sources",
    ["sources-utm"],
    { view: "utm" }
  );

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">
            Traffic Sources
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              <TabsTrigger value="referrers">Referrers</TabsTrigger>
              <TabsTrigger value="utm">UTM Campaigns</TabsTrigger>
            </TabsList>
            <TabsContent value="referrers" className="mt-4">
              <DataTable
                columns={referrerColumns}
                data={referrers ?? []}
                loading={refLoading}
                searchColumn="referrerDomain"
                searchPlaceholder="Search sources..."
                emptyMessage="No referrer data"
              />
            </TabsContent>
            <TabsContent value="utm" className="mt-4">
              <DataTable
                columns={utmColumns}
                data={utm ?? []}
                loading={utmLoading}
                emptyMessage="No UTM data"
              />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
