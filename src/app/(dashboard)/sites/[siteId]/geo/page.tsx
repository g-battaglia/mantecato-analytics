"use client";

import { useState, useMemo } from "react";
import { type ColumnDef } from "@tanstack/react-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { DataTable } from "@/components/data/DataTable";
import { WorldMap } from "@/components/charts/WorldMap";
import { useSiteQuery } from "@/hooks/use-site-query";
import { ArrowLeft } from "lucide-react";

interface GeoRow {
  country: string;
  region: string | null;
  city: string | null;
  visitors: number;
  pageviews: number;
  visits: number;
}

const numCols: ColumnDef<GeoRow>[] = [
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
    accessorKey: "visits",
    header: () => <span className="flex justify-end">Visits</span>,
    cell: ({ getValue }) => (
      <span className="flex justify-end tabular-nums">
        {(getValue() as number).toLocaleString()}
      </span>
    ),
  },
];

const countryColumns: ColumnDef<GeoRow>[] = [
  { accessorKey: "country", header: "Country", enableSorting: false },
  ...numCols,
];

const regionColumns: ColumnDef<GeoRow>[] = [
  {
    accessorKey: "region",
    header: "Region",
    cell: ({ getValue }) => (getValue() as string) ?? "--",
    enableSorting: false,
  },
  ...numCols,
];

const cityColumns: ColumnDef<GeoRow>[] = [
  {
    accessorKey: "city",
    header: "City",
    cell: ({ getValue }) => (getValue() as string) ?? "--",
    enableSorting: false,
  },
  ...numCols,
];

export default function GeoPage() {
  const [level, setLevel] = useState<"country" | "region" | "city">("country");
  const [selectedCountry, setSelectedCountry] = useState<string | null>(null);
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);

  const extraParams: Record<string, string> = { level };
  if (selectedCountry) extraParams.country = selectedCountry;
  if (selectedRegion) extraParams.region = selectedRegion;

  const { data, isLoading } = useSiteQuery<GeoRow[]>(
    "geo",
    ["geo", level, selectedCountry ?? "", selectedRegion ?? ""],
    extraParams
  );

  function handleCountryClick(row: GeoRow) {
    setSelectedCountry(row.country);
    setLevel("region");
  }

  function handleRegionClick(row: GeoRow) {
    if (row.region) {
      setSelectedRegion(row.region);
      setLevel("city");
    }
  }

  function handleBack() {
    if (level === "city") {
      setSelectedRegion(null);
      setLevel("region");
    } else if (level === "region") {
      setSelectedCountry(null);
      setLevel("country");
    }
  }

  const title =
    level === "city"
      ? `Cities in ${selectedRegion}, ${selectedCountry}`
      : level === "region"
        ? `Regions in ${selectedCountry}`
        : "Countries";

  // Map data: only used at country level
  const mapData = useMemo(() => {
    if (level !== "country" || !data) return [];
    return data.map((r) => ({ country: r.country, visitors: r.visitors }));
  }, [data, level]);

  function handleMapCountryClick(code: string) {
    setSelectedCountry(code);
    setLevel("region");
  }

  return (
    <div className="space-y-4">
      {/* World map — only shown at country level */}
      {level === "country" && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Visitor Map
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-[340px] w-full" />
            ) : (
              <WorldMap
                data={mapData}
                onCountryClick={handleMapCountryClick}
              />
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            {level !== "country" && (
              <Button variant="ghost" size="sm" onClick={handleBack}>
                <ArrowLeft className="h-4 w-4" />
              </Button>
            )}
            <CardTitle className="text-sm font-medium">{title}</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <DataTable
            columns={
              level === "city"
                ? cityColumns
                : level === "region"
                  ? regionColumns
                  : countryColumns
            }
            data={data ?? []}
            loading={isLoading}
            emptyMessage="No geographic data"
            onRowClick={
              level === "country"
                ? handleCountryClick
                : level === "region"
                  ? handleRegionClick
                  : undefined
            }
          />
        </CardContent>
      </Card>
    </div>
  );
}
