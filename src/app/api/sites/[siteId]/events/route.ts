import { NextRequest, NextResponse } from "next/server";
import { getSession, canAccessWebsite } from "@/lib/auth";
import { resolveDateRange } from "@/lib/date";
import type { DateRangePreset } from "@/lib/constants";
import { parseFiltersFromParams } from "@/lib/queries";
import {
  getEventMetrics,
  getEventProperties,
  getEventTimeSeries,
} from "@/queries/events";

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
  const eventName = sp.get("event");
  const granularity = sp.get("granularity") || "day";
  const section = sp.get("section");
  const filters = parseFiltersFromParams(sp);

  try {
    // Detail view for a specific event
    if (eventName) {
      if (section === "timeseries") {
        const timeseries = await getEventTimeSeries(
          siteId,
          eventName,
          startDate,
          endDate,
          granularity,
          filters
        );
        return NextResponse.json(timeseries);
      }

      if (section === "properties") {
        const properties = await getEventProperties(
          siteId,
          eventName,
          startDate,
          endDate
        );
        return NextResponse.json(properties);
      }

      // Default: return both timeseries + properties for the event
      const [timeseries, properties] = await Promise.all([
        getEventTimeSeries(siteId, eventName, startDate, endDate, granularity, filters),
        getEventProperties(siteId, eventName, startDate, endDate),
      ]);
      return NextResponse.json({ timeseries, properties });
    }

    const events = await getEventMetrics(
      siteId,
      startDate,
      endDate,
      50,
      filters
    );
    return NextResponse.json(events);
  } catch (error) {
    console.error("Events query error:", error);
    return NextResponse.json(
      { error: "Failed to fetch events" },
      { status: 500 }
    );
  }
}
