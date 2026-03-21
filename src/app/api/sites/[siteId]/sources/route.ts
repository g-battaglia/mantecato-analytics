import { NextRequest, NextResponse } from "next/server";
import { getSession, canAccessWebsite } from "@/lib/auth";
import { resolveDateRange } from "@/lib/date";
import type { DateRangePreset } from "@/lib/constants";
import { parseFiltersFromParams } from "@/lib/queries";
import { getReferrerMetrics, getUTMMetrics } from "@/queries/sources";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ siteId: string }> }
) {
  const { siteId } = await params;
  const session = await getSession();
  if (!session)
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  if (!(await canAccessWebsite(session.userId, session.role, siteId)))
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });

  const sp = request.nextUrl.searchParams;
  const preset = (sp.get("range") || "30d") as DateRangePreset;
  const range = resolveDateRange(preset);
  const startDate =
    preset === "custom" && sp.get("start")
      ? new Date(sp.get("start")!)
      : range?.startDate ?? new Date("2020-01-01");
  const endDate =
    preset === "custom" && sp.get("end")
      ? new Date(sp.get("end")!)
      : range?.endDate ?? new Date();
  const view = sp.get("view") || "referrers";
  const filters = parseFiltersFromParams(sp);

  try {
    if (view === "utm") {
      const groupBy = (sp.get("groupBy") || "utm_source") as
        | "utm_source"
        | "utm_medium"
        | "utm_campaign";
      const utm = await getUTMMetrics(
        siteId,
        startDate,
        endDate,
        groupBy,
        50,
        filters
      );
      return NextResponse.json(utm);
    }

    const referrers = await getReferrerMetrics(
      siteId,
      startDate,
      endDate,
      50,
      filters
    );
    return NextResponse.json(referrers);
  } catch (error) {
    console.error("Sources query error:", error);
    return NextResponse.json(
      { error: "Failed to fetch sources" },
      { status: 500 }
    );
  }
}
