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
import { Globe } from "lucide-react";
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
      <SelectTrigger className="w-full h-14 py-2 text-left">
        <Globe className="mr-2 h-4 w-4 shrink-0 opacity-50" />
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
