import { redirect } from "next/navigation";
import { getSession, getUserWebsites } from "@/lib/auth";
import { Header } from "@/components/layout/Header";

export default async function HomePage() {
  const session = await getSession();
  if (!session) redirect("/login");

  const websites = await getUserWebsites(session.userId, session.role);

  if (websites.length === 1) {
    redirect(`/sites/${websites[0].website_id}`);
  }

  return (
    <>
      <Header title="Sites" />
      <div className="flex-1 p-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {websites.map((site) => (
            <a
              key={site.website_id}
              href={`/sites/${site.website_id}`}
              className="group rounded-lg border bg-card p-4 transition-colors hover:bg-accent"
            >
              <h3 className="font-medium group-hover:text-accent-foreground">
                {site.name}
              </h3>
              {site.domain && (
                <p className="mt-1 text-sm text-muted-foreground">
                  {site.domain}
                </p>
              )}
            </a>
          ))}
          {websites.length === 0 && (
            <p className="col-span-full text-center text-muted-foreground">
              No websites found. Add websites through Umami.
            </p>
          )}
        </div>
      </div>
    </>
  );
}
