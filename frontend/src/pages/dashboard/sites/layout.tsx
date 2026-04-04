import { useParams, Outlet, Navigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Header } from "@/components/layout/Header";
import { FilterBar } from "@/components/filters/FilterBar";
import { apiFetch } from "@/lib/api";

interface SiteInfo {
  websiteId: string;
  name: string;
  domain: string | null;
  shareId: string | null;
}

/**
 * Site-level layout. Fetches site info, renders the header with site name +
 * share button, the filter bar, and wraps page content in a scrollable
 * padded container.
 */
export function SiteLayout() {
  const { siteId } = useParams<{ siteId: string }>();

  const { data: sites, isLoading, isError } = useQuery<SiteInfo[]>({
    queryKey: ["sites"],
    queryFn: async () => {
      const res = await apiFetch("/api/sites");
      if (!res.ok) throw new Error("Failed to fetch sites");
      return res.json();
    },
    staleTime: 60_000,
  });

  if (isLoading) return null;

  if (isError || !sites) {
    return <Navigate to="/" replace />;
  }

  const site = sites.find((s) => s.websiteId === siteId);

  if (!site) {
    return <Navigate to="/" replace />;
  }

  return (
    <>
      <Header title={site.name} shareId={site.shareId} />
      <FilterBar />
      <div className="flex-1 overflow-auto p-4">
        <Outlet />
      </div>
    </>
  );
}
