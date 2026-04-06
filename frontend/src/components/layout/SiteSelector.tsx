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
      <p className="px-2 text-xs text-muted-foreground">No websites found</p>
    );
  }

  return (
    <Select
      value={currentSiteId ?? ""}
      onValueChange={(value) => {
        navigate(`/sites/${value}`);
      }}
    >
      <SelectTrigger className="h-9 w-full border-0 bg-transparent px-2 py-1 text-left shadow-none hover:bg-transparent focus-visible:border-transparent focus-visible:ring-0 dark:bg-transparent dark:hover:bg-transparent">
        <SelectValue placeholder="Select a site" />
      </SelectTrigger>
      <SelectContent>
        {websites.map((site) => (
          <SelectItem key={site.websiteId} value={site.websiteId}>
            <div className="flex flex-col">
              <span>{site.name}</span>
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
