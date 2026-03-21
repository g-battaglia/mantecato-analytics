import { NextRequest, NextResponse } from "next/server";
import { getSession, canAccessWebsite } from "@/lib/auth";
import { resolveDateRange } from "@/lib/date";
import type { DateRangePreset } from "@/lib/constants";
import { parseFiltersFromParams } from "@/lib/queries";
import {
  getDurationDistribution,
  getDurationPercentiles,
  getDurationByPage,
  getBounceRateByPage,
  getBounceRateBySource,
} from "@/queries/engagement";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ siteId: string }> }
) {
  const { siteId } = await params;
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const hasAccess = await canAccessWebsite(session.userId, session.role, siteId);
  if (!hasAccess) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const searchParams = request.nextUrl.searchParams;
  const preset = (searchParams.get("range") || "30d") as DateRangePreset;
  const customStart = searchParams.get("start");
  const customEnd = searchParams.get("end");
  const filters = parseFiltersFromParams(searchParams);

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
    const [distribution, percentiles, durationByPage, bounceByPage, bounceBySource] =
      await Promise.all([
        getDurationDistribution(siteId, startDate, endDate, filters),
        getDurationPercentiles(siteId, startDate, endDate, filters),
        getDurationByPage(siteId, startDate, endDate, 20, filters),
        getBounceRateByPage(siteId, startDate, endDate, 20, filters),
        getBounceRateBySource(siteId, startDate, endDate, 20, filters),
      ]);

    return NextResponse.json({
      distribution,
      percentiles,
      durationByPage,
      bounceByPage,
      bounceBySource,
    });
  } catch (error) {
    console.error("Engagement query error:", error);
    return NextResponse.json(
      { error: "Failed to fetch engagement data" },
      { status: 500 }
    );
  }
}
