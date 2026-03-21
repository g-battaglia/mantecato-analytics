import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { resolveDateRange, getComparisonRange } from "@/lib/date";
import type { DateRangePreset } from "@/lib/constants";
import {
  getWebsiteStats,
  getPageviewTimeSeries,
  getTopPages,
  getTopReferrers,
  getTopEvents,
  getDeviceBreakdown,
  getCountryBreakdown,
} from "@/queries/stats";

/**
 * Public stats endpoint — no auth required.
 * Looks up the website by its share_id instead of website_id.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ shareId: string }> }
) {
  const { shareId } = await params;

  // Look up website by share_id
  const website = await prisma.website.findFirst({
    where: { shareId, deleted_at: null },
    select: { website_id: true, name: true, domain: true },
  });

  if (!website) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const siteId = website.website_id;
  const searchParams = request.nextUrl.searchParams;
  const preset = (searchParams.get("range") || "30d") as DateRangePreset;
  const customStart = searchParams.get("start");
  const customEnd = searchParams.get("end");
  const granularity = searchParams.get("granularity") || "day";

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

  const prevRange = getComparisonRange(
    { startDate, endDate },
    "previous_period"
  );

  try {
    const [stats, previousStats, timeseries, previousTimeseries, pages, referrers, events, browsers, countries] =
      await Promise.all([
        getWebsiteStats(siteId, startDate, endDate),
        getWebsiteStats(siteId, prevRange.startDate, prevRange.endDate),
        getPageviewTimeSeries(siteId, startDate, endDate, granularity),
        getPageviewTimeSeries(siteId, prevRange.startDate, prevRange.endDate, granularity),
        getTopPages(siteId, startDate, endDate, 10),
        getTopReferrers(siteId, startDate, endDate, 10),
        getTopEvents(siteId, startDate, endDate, 10),
        getDeviceBreakdown(siteId, startDate, endDate, "browser", 10),
        getCountryBreakdown(siteId, startDate, endDate, 10),
      ]);

    return NextResponse.json({
      website: { name: website.name, domain: website.domain },
      stats,
      previousStats,
      timeseries,
      previousTimeseries,
      pages,
      referrers,
      events,
      browsers,
      countries,
    });
  } catch (error) {
    console.error("Share stats query error:", error);
    return NextResponse.json(
      { error: "Failed to fetch stats" },
      { status: 500 }
    );
  }
}
