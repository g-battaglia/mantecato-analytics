import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { Header } from "@/components/layout/Header";
import { Globe, ArrowRight } from "lucide-react";
import { apiFetch } from "@/lib/api";

export function HomePage() {
  const navigate = useNavigate();
  const { data: websites = [] } = useQuery<
    Array<{ websiteId: string; name: string; domain: string }>
  >({
    queryKey: ["sites"],
    queryFn: async () => {
      const res = await apiFetch("/api/sites");
      if (!res.ok) throw new Error("Failed to fetch sites");
      return res.json();
    },
  });

  useEffect(() => {
    if (websites.length === 1) {
      navigate(`/sites/${websites[0].websiteId}`, { replace: true });
    }
  }, [websites, navigate]);

  return (
    <>
      <Header title="Sites" />
      <div className="flex-1 p-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {websites.map((site) => (
            <a
              key={site.websiteId}
              href={`/sites/${site.websiteId}`}
              className="group relative flex flex-col gap-3 rounded-xl border bg-card p-5 transition-all hover:border-primary/30 hover:bg-accent hover:shadow-md"
            >
              <div className="flex items-start justify-between">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Globe className="h-5 w-5" />
                </div>
                <ArrowRight className="h-4 w-4 text-muted-foreground/0 transition-all group-hover:text-muted-foreground group-hover:translate-x-0.5" />
              </div>
              <div>
                <h3 className="font-semibold tracking-tight group-hover:text-accent-foreground">
                  {site.name}
                </h3>
                {site.domain && (
                  <p className="mt-0.5 truncate text-sm text-muted-foreground">
                    {site.domain}
                  </p>
                )}
              </div>
            </a>
          ))}
          {websites.length === 0 && (
            <div className="col-span-full flex flex-col items-center justify-center py-16 text-center">
              <Globe className="mb-3 h-10 w-10 text-muted-foreground/30" />
              <p className="text-muted-foreground">
                No websites found.
              </p>
              <p className="mt-1 text-sm text-muted-foreground/60">
                Add websites through the Umami admin panel.
              </p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
