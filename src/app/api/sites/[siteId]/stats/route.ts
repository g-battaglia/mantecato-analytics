import { NextRequest, NextResponse } from "next/server";
import { getSession, canAccessWebsite } from "@/lib/auth";
import { resolveDateRange, getComparisonRange } from "@/lib/date";
import type { DateRangePreset } from "@/lib/constants";
import { parseFiltersFromParams } from "@/lib/queries";
import {
  getWebsiteStats,
  getPageviewTimeSeries,
  getTopPages,
  getTopReferrers,
  getTopEvents,
  getDeviceBreakdown,
  getCountryBreakdown,
} from "@/queries/stats";

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
  const preset = (searchParams.get("range") || "30d") as DateRangePreset;
  const customStart = searchParams.get("start");
  const customEnd = searchParams.get("end");
  const granularity = searchParams.get("granularity") || "day";
  const section = searchParams.get("section");
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

  // Calculate previous period for comparison
  const prevRange = getComparisonRange(
    { startDate, endDate },
    "previous_period"
  );

  try {
    if (section) {
      switch (section) {
        case "metrics": {
          const stats = await getWebsiteStats(siteId, startDate, endDate, filters);
          return NextResponse.json(stats);
        }
        case "timeseries": {
          const timeseries = await getPageviewTimeSeries(siteId, startDate, endDate, granularity, filters);
          return NextResponse.json(timeseries);
        }
        case "pages": {
          const pages = await getTopPages(siteId, startDate, endDate, 10, filters);
          return NextResponse.json(pages);
        }
        case "referrers": {
          const referrers = await getTopReferrers(siteId, startDate, endDate, 10, filters);
          return NextResponse.json(referrers);
        }
        case "events": {
          const events = await getTopEvents(siteId, startDate, endDate, 10, filters);
          return NextResponse.json(events);
        }
        case "browsers": {
          const browsers = await getDeviceBreakdown(siteId, startDate, endDate, "browser", 10, filters);
          return NextResponse.json(browsers);
        }
        case "os": {
          const os = await getDeviceBreakdown(siteId, startDate, endDate, "os", 10, filters);
          return NextResponse.json(os);
        }
        case "devices": {
          const devices = await getDeviceBreakdown(siteId, startDate, endDate, "device", 10, filters);
          return NextResponse.json(devices);
        }
        case "countries": {
          const countries = await getCountryBreakdown(siteId, startDate, endDate, 10, filters);
          return NextResponse.json(countries);
        }
      }
    }

    const [stats, previousStats, timeseries, previousTimeseries, pages, referrers, events, browsers, countries] =
      await Promise.all([
        getWebsiteStats(siteId, startDate, endDate, filters),
        getWebsiteStats(siteId, prevRange.startDate, prevRange.endDate, filters),
        getPageviewTimeSeries(siteId, startDate, endDate, granularity, filters),
        getPageviewTimeSeries(siteId, prevRange.startDate, prevRange.endDate, granularity, filters),
        getTopPages(siteId, startDate, endDate, 10, filters),
        getTopReferrers(siteId, startDate, endDate, 10, filters),
        getTopEvents(siteId, startDate, endDate, 10, filters),
        getDeviceBreakdown(siteId, startDate, endDate, "browser", 10, filters),
        getCountryBreakdown(siteId, startDate, endDate, 10, filters),
      ]);

    return NextResponse.json({
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
    console.error("Stats query error:", error);
    return NextResponse.json(
      { error: "Failed to fetch stats" },
      { status: 500 }
    );
  }
}
