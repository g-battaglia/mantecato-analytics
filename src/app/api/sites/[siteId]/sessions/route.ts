import { NextRequest, NextResponse } from "next/server";
import { getSession, canAccessWebsite } from "@/lib/auth";
import { resolveDateRange } from "@/lib/date";
import type { DateRangePreset } from "@/lib/constants";
import { getSessionList, getSessionActivity } from "@/queries/sessions";

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
  const sessionId = sp.get("sessionId");

  // Detail view for a specific session
  if (sessionId) {
    try {
      const activity = await getSessionActivity(sessionId, siteId);
      return NextResponse.json(activity);
    } catch (error) {
      console.error("Session activity query error:", error);
      return NextResponse.json(
        { error: "Failed to fetch session activity" },
        { status: 500 }
      );
    }
  }

  // List view
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
  const limit = Number(sp.get("limit") || 50);
  const offset = Number(sp.get("offset") || 0);

  try {
    const sessions = await getSessionList(
      siteId,
      startDate,
      endDate,
      limit,
      offset
    );
    return NextResponse.json(sessions);
  } catch (error) {
    console.error("Sessions query error:", error);
    return NextResponse.json(
      { error: "Failed to fetch sessions" },
      { status: 500 }
    );
  }
}
