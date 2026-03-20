import { NextRequest, NextResponse } from "next/server";
import { getSession, canAccessWebsite } from "@/lib/auth";
import { resolveDateRange, getComparisonRange } from "@/lib/date";
import type { DateRangePreset } from "@/lib/constants";
import { getComparisonStats } from "@/queries/compare";

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
  const compareMode = (sp.get("compare") || "previous_period") as
    | "previous_period"
    | "previous_year";

  const range = resolveDateRange(preset);
  if (!range) {
    return NextResponse.json(
      { error: "Invalid date range for comparison" },
      { status: 400 }
    );
  }

  const compRange = getComparisonRange(range, compareMode);

  try {
    const stats = await getComparisonStats(
      siteId,
      range.startDate,
      range.endDate,
      compRange.startDate,
      compRange.endDate
    );
    return NextResponse.json({
      current: stats.find((s) => s.period === "current"),
      previous: stats.find((s) => s.period === "previous"),
      currentRange: {
        start: range.startDate.toISOString(),
        end: range.endDate.toISOString(),
      },
      previousRange: {
        start: compRange.startDate.toISOString(),
        end: compRange.endDate.toISOString(),
      },
    });
  } catch (error) {
    console.error("Compare query error:", error);
    return NextResponse.json(
      { error: "Failed to fetch comparison data" },
      { status: 500 }
    );
  }
}
