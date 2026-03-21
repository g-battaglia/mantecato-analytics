import { NextRequest, NextResponse } from "next/server";
import { getSession, canAccessWebsite } from "@/lib/auth";
import { resolveDateRange } from "@/lib/date";
import type { DateRangePreset } from "@/lib/constants";
import { getJourneys } from "@/queries/journeys";

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
  const pathLength = Number(sp.get("pathLength") || 3);
  const limit = Number(sp.get("limit") || 20);

  try {
    const journeys = await getJourneys(
      siteId,
      startDate,
      endDate,
      pathLength,
      limit
    );
    return NextResponse.json(journeys);
  } catch (error) {
    console.error("Journeys query error:", error);
    return NextResponse.json(
      { error: "Failed to fetch journey data" },
      { status: 500 }
    );
  }
}
