import { NextRequest, NextResponse } from "next/server";
import { getSession, canAccessWebsite } from "@/lib/auth";
import { resolveDateRange } from "@/lib/date";
import type { DateRangePreset } from "@/lib/constants";
import { getFilterValues } from "@/queries/filter-values";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ siteId: string }> }
) {
  const { siteId } = await params;
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const hasAccess = await canAccessWebsite(
    session.userId,
    session.role,
    siteId
  );
  if (!hasAccess) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const searchParams = request.nextUrl.searchParams;
  const column = searchParams.get("column");
  const search = searchParams.get("search") || undefined;
  const preset = (searchParams.get("range") || "30d") as DateRangePreset;
  const customStart = searchParams.get("start");
  const customEnd = searchParams.get("end");

  if (!column) {
    return NextResponse.json(
      { error: "Missing column parameter" },
      { status: 400 }
    );
  }

  let startDate: Date;
  let endDate: Date;

  if (preset === "custom" && customStart && customEnd) {
    startDate = new Date(customStart);
    endDate = new Date(customEnd);
  } else {
    const range = resolveDateRange(preset);
    if (!range) {
      startDate = new Date("2020-01-01");
      endDate = new Date();
    } else {
      startDate = range.startDate;
      endDate = range.endDate;
    }
  }

  try {
    const values = await getFilterValues(
      siteId,
      column,
      startDate,
      endDate,
      search
    );
    return NextResponse.json(values);
  } catch (error) {
    console.error("Filter values query error:", error);
    return NextResponse.json(
      { error: "Failed to fetch filter values" },
      { status: 500 }
    );
  }
}
