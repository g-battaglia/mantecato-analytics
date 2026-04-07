import { useNavigate, useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useFiltersStore } from "@/stores/filters";
import { apiFetch } from "@/lib/api";

interface Website {
  websiteId: string;
  name: string;
  domain: string | null;
}

async function fetchWebsites(): Promise<Website[]> {
  const res = await apiFetch("/api/sites");
  if (!res.ok) throw new Error("Failed to fetch websites");
  return res.json();
}

export function SiteSelector() {
  const navigate = useNavigate();
  const params = useParams();
  const currentSiteId = params.siteId as string | undefined;
  const clearFilters = useFiltersStore((s) => s.clearFilters);

  const { data: websites, isLoading } = useQuery({
    queryKey: ["websites"],
    queryFn: fetchWebsites,
    staleTime: 300_000,
  });

  if (isLoading) {
    return <Skeleton className="h-9 w-full" />;
  }

  if (!websites?.length) {
    return (
      <p className="px-2 text-sm text-muted-foreground">No websites found</p>
    );
  }

  return (
    <Select
      value={currentSiteId ?? ""}
      onValueChange={(value) => {
        if (value !== currentSiteId) clearFilters();
        navigate(`/sites/${value}`);
      }}
    >
      <SelectTrigger className="h-9 w-full border-0 bg-transparent px-2 py-1 text-left shadow-none rounded-lg hover:bg-muted/50 transition-colors duration-150 focus-visible:border-transparent focus-visible:ring-0 dark:bg-transparent dark:hover:bg-muted/30">
        <SelectValue placeholder="Select a site" />
      </SelectTrigger>
      <SelectContent position="popper" side="bottom" sideOffset={4} className="min-w-[260px] p-2 pb-3">
        {websites.map((site) => (
          <SelectItem
            key={site.websiteId}
            value={site.websiteId}
            className="py-3 px-3 rounded-md"
          >
            <div className="flex flex-col gap-0.5">
              <span className="text-sm font-medium">{site.name}</span>
              {site.domain && (
                <span className="text-xs text-muted-foreground">
                  {site.domain}
                </span>
              )}
            </div>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
