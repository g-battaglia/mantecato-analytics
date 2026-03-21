import { NextRequest, NextResponse } from "next/server";
import { getSession, canAccessWebsite } from "@/lib/auth";
import { resolveDateRange } from "@/lib/date";
import type { DateRangePreset } from "@/lib/constants";
import { getFunnel } from "@/queries/funnels";

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

  // Steps come as JSON in the "steps" param
  const stepsParam = sp.get("steps");
  if (!stepsParam) {
    return NextResponse.json(
      { error: "Missing steps parameter" },
      { status: 400 }
    );
  }

  let steps: Array<{ type: "url" | "event"; value: string }>;
  try {
    steps = JSON.parse(stepsParam);
  } catch {
    return NextResponse.json(
      { error: "Invalid steps parameter" },
      { status: 400 }
    );
  }

  if (!Array.isArray(steps) || steps.length < 2) {
    return NextResponse.json(
      { error: "At least 2 steps are required" },
      { status: 400 }
    );
  }

  const windowMinutes = Number(sp.get("window") || 60);

  try {
    const funnel = await getFunnel(
      siteId,
      startDate,
      endDate,
      steps,
      windowMinutes
    );
    return NextResponse.json(funnel);
  } catch (error) {
    console.error("Funnel query error:", error);
    return NextResponse.json(
      { error: "Failed to fetch funnel data" },
      { status: 500 }
    );
  }
}
