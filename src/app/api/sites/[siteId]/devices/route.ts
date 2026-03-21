import { NextRequest, NextResponse } from "next/server";
import { getSession, canAccessWebsite } from "@/lib/auth";
import { resolveDateRange } from "@/lib/date";
import type { DateRangePreset } from "@/lib/constants";
import { parseFiltersFromParams } from "@/lib/queries";
import { getDeviceMetrics } from "@/queries/devices";

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
  const filters = parseFiltersFromParams(sp);

  try {
    const [browsers, os, devices, screens, languages] = await Promise.all([
      getDeviceMetrics(siteId, startDate, endDate, "browser", 20, filters),
      getDeviceMetrics(siteId, startDate, endDate, "os", 20, filters),
      getDeviceMetrics(siteId, startDate, endDate, "device", 20, filters),
      getDeviceMetrics(siteId, startDate, endDate, "screen", 20, filters),
      getDeviceMetrics(siteId, startDate, endDate, "language", 20, filters),
    ]);

    return NextResponse.json({ browsers, os, devices, screens, languages });
  } catch (error) {
    console.error("Devices query error:", error);
    return NextResponse.json(
      { error: "Failed to fetch devices" },
      { status: 500 }
    );
  }
}
