import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { listDashboards, createDashboard } from "@/queries/dashboards";
import { createEmptyDashboard } from "@/lib/dashboard-types";

/**
 * GET /api/dashboards — list all dashboards for the current user.
 * Optional ?siteId= filter.
 */
export async function GET(request: NextRequest) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const siteId = request.nextUrl.searchParams.get("siteId") ?? undefined;

  try {
    const dashboards = await listDashboards(session.userId, siteId);
    return NextResponse.json(dashboards);
  } catch (error) {
    console.error("List dashboards error:", error);
    return NextResponse.json(
      { error: "Failed to list dashboards" },
      { status: 500 }
    );
  }
}

/**
 * POST /api/dashboards — create a new dashboard.
 * Body: { name, description?, websiteId }
 */
export async function POST(request: NextRequest) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const body = await request.json();
    const { name, description, websiteId } = body as {
      name: string;
      description?: string;
      websiteId: string;
    };

    if (!name || !websiteId) {
      return NextResponse.json(
        { error: "name and websiteId are required" },
        { status: 400 }
      );
    }

    const dashboard = await createDashboard(
      session.userId,
      websiteId,
      name,
      description ?? "",
      createEmptyDashboard()
    );

    return NextResponse.json(dashboard, { status: 201 });
  } catch (error) {
    console.error("Create dashboard error:", error);
    return NextResponse.json(
      { error: "Failed to create dashboard" },
      { status: 500 }
    );
  }
}
