import { NextRequest, NextResponse } from "next/server";
import { getSession, canAccessWebsite } from "@/lib/auth";
import {
  getActiveVisitors,
  getRecentEvents,
  getCurrentPages,
} from "@/queries/realtime";

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

  try {
    const [active, events, pages] = await Promise.all([
      getActiveVisitors(siteId),
      getRecentEvents(siteId),
      getCurrentPages(siteId),
    ]);

    return NextResponse.json({ active, events, pages });
  } catch (error) {
    console.error("Realtime query error:", error);
    return NextResponse.json(
      { error: "Failed to fetch realtime data" },
      { status: 500 }
    );
  }
}
