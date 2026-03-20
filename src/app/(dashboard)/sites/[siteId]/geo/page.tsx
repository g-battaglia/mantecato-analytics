"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { DataTable, type Column } from "@/components/data/DataTable";
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

const countryColumns: Column<GeoRow>[] = [
  { key: "country", label: "Country" },
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
    key: "visits",
    label: "Visits",
    align: "right",
    render: (row) => row.visits.toLocaleString(),
  },
];

const regionColumns: Column<GeoRow>[] = [
  { key: "region", label: "Region", render: (row) => row.region ?? "--" },
  ...countryColumns.slice(1),
];

const cityColumns: Column<GeoRow>[] = [
  { key: "city", label: "City", render: (row) => row.city ?? "--" },
  ...countryColumns.slice(1),
];

export default function GeoPage() {
  const [level, setLevel] = useState<"country" | "region" | "city">("country");
  const [selectedCountry, setSelectedCountry] = useState<string | null>(null);
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);

  const extraParams: Record<string, string> = { level };
  if (selectedCountry) extraParams.country = selectedCountry;
  if (selectedRegion) extraParams.region = selectedRegion;

  const { data, isLoading } = useSiteQuery<GeoRow[]>("geo", ["geo", level, selectedCountry ?? "", selectedRegion ?? ""], extraParams);

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

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            {level !== "country" && (
              <Button variant="ghost" size="icon-sm" onClick={handleBack}>
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
            rowKey={(row) =>
              `${row.country}-${row.region ?? ""}-${row.city ?? ""}`
            }
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
