"use client";

import { type ColumnDef } from "@tanstack/react-table";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { MetricCard } from "@/components/data/MetricCard";
import { AreaChart } from "@/components/charts/AreaChart";
import { DataTable } from "@/components/data/DataTable";
import { useSiteQuery } from "@/hooks/use-site-query";
import { formatCurrency } from "@/lib/format";

interface RevenueSummary {
  totalRevenue: number;
  transactions: number;
  uniqueCustomers: number;
  arpu: number;
}

interface RevenueTimeSeries {
  time: string;
  revenue: number;
  transactions: number;
}

interface RevenueByEvent {
  eventName: string;
  revenue: number;
  transactions: number;
  avgRevenue: number;
}

interface RevenueByCountry {
  country: string;
  revenue: number;
  transactions: number;
}

interface RevenueData {
  summary: RevenueSummary;
  timeseries: RevenueTimeSeries[];
  byEvent: RevenueByEvent[];
  byCountry: RevenueByCountry[];
}

const eventColumns: ColumnDef<RevenueByEvent>[] = [
  {
    accessorKey: "eventName",
    header: "Event",
    cell: ({ getValue }) => (
      <span className="font-mono text-xs">{getValue() as string}</span>
    ),
    enableSorting: false,
  },
  {
    accessorKey: "revenue",
    header: () => <span className="flex justify-end">Revenue</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {formatCurrency(getValue() as number)}
      </span>
    ),
  },
  {
    accessorKey: "transactions",
    header: () => <span className="flex justify-end">Transactions</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toLocaleString()}
      </span>
    ),
  },
  {
    accessorKey: "avgRevenue",
    header: () => <span className="flex justify-end">Avg Value</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {formatCurrency(getValue() as number)}
      </span>
    ),
  },
];

const countryColumns: ColumnDef<RevenueByCountry>[] = [
  {
    accessorKey: "country",
    header: "Country",
    enableSorting: false,
  },
  {
    accessorKey: "revenue",
    header: () => <span className="flex justify-end">Revenue</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {formatCurrency(getValue() as number)}
      </span>
    ),
  },
  {
    accessorKey: "transactions",
    header: () => <span className="flex justify-end">Transactions</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toLocaleString()}
      </span>
    ),
  },
];

export default function RevenuePage() {
  const { data, isLoading } = useSiteQuery<RevenueData>("revenue", [
    "revenue",
  ]);

  const summary = data?.summary;

  return (
    <div className="space-y-4">
      {/* Summary metrics */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Total Revenue"
          value={summary?.totalRevenue ?? null}
          format="number"
          loading={isLoading}
        />
        <MetricCard
          label="Transactions"
          value={summary?.transactions ?? null}
          loading={isLoading}
        />
        <MetricCard
          label="Customers"
          value={summary?.uniqueCustomers ?? null}
          loading={isLoading}
        />
        <MetricCard
          label="ARPU"
          value={summary?.arpu ?? null}
          format="number"
          loading={isLoading}
        />
      </div>

      {/* Revenue time series */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">
            Revenue Over Time
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-[300px] w-full" />
          ) : data?.timeseries && data.timeseries.length > 0 ? (
            <AreaChart
              data={data.timeseries}
              xKey="time"
              yKeys={["revenue"]}
              labels={{ revenue: "Revenue" }}
            />
          ) : (
            <p className="py-12 text-center text-sm text-muted-foreground">
              No revenue data available
            </p>
          )}
        </CardContent>
      </Card>

      {/* Breakdowns */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Revenue by Event
            </CardTitle>
          </CardHeader>
          <CardContent>
            <DataTable
              columns={eventColumns}
              data={data?.byEvent ?? []}
              loading={isLoading}
              emptyMessage="No revenue events"
              showPagination={false}
              compact
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Revenue by Country
            </CardTitle>
          </CardHeader>
          <CardContent>
            <DataTable
              columns={countryColumns}
              data={data?.byCountry ?? []}
              loading={isLoading}
              emptyMessage="No revenue by country"
              showPagination={false}
              compact
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
