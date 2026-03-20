"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable, type Column } from "@/components/data/DataTable";
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

const referrerColumns: Column<ReferrerRow>[] = [
  { key: "referrerDomain", label: "Source" },
  {
    key: "visitors",
    label: "Visitors",
    align: "right",
    render: (row) => row.visitors.toLocaleString(),
  },
  {
    key: "pageviews",
    label: "Pageviews",
    align: "right",
    render: (row) => row.pageviews.toLocaleString(),
  },
  {
    key: "bounceRate",
    label: "Bounce Rate",
    align: "right",
    render: (row) => formatPercent(row.bounceRate),
  },
  {
    key: "avgDuration",
    label: "Avg Duration",
    align: "right",
    render: (row) => formatDuration(row.avgDuration),
  },
];

const utmColumns: Column<UTMRow>[] = [
  { key: "utmSource", label: "Source", render: (row) => row.utmSource ?? "--" },
  { key: "utmMedium", label: "Medium", render: (row) => row.utmMedium ?? "--" },
  {
    key: "utmCampaign",
    label: "Campaign",
    render: (row) => row.utmCampaign ?? "--",
  },
  {
    key: "visitors",
    label: "Visitors",
    align: "right",
    render: (row) => row.visitors.toLocaleString(),
  },
  {
    key: "pageviews",
    label: "Pageviews",
    align: "right",
    render: (row) => row.pageviews.toLocaleString(),
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
                rowKey={(row) => row.referrerDomain}
                emptyMessage="No referrer data"
              />
            </TabsContent>
            <TabsContent value="utm" className="mt-4">
              <DataTable
                columns={utmColumns}
                data={utm ?? []}
                loading={utmLoading}
                rowKey={(row) =>
                  `${row.utmSource}-${row.utmMedium}-${row.utmCampaign}`
                }
                emptyMessage="No UTM data"
              />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
