import { redirect } from "next/navigation";
import { getSession, canAccessWebsite } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { Header } from "@/components/layout/Header";
import { FilterBar } from "@/components/filters/FilterBar";

export default async function SiteLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ siteId: string }>;
}) {
  const { siteId } = await params;
  const session = await getSession();
  if (!session) redirect("/login");

  const hasAccess = await canAccessWebsite(
    session.userId,
    session.role,
    siteId
  );
  if (!hasAccess) redirect("/");

  const website = await prisma.website.findUnique({
    where: { website_id: siteId },
    select: { name: true, domain: true, shareId: true },
  });

  if (!website) redirect("/");

  return (
    <>
      <Header title={website.name} shareId={website.shareId} />
      <FilterBar />
      <div className="flex-1 overflow-auto p-4">{children}</div>
    </>
  );
}
