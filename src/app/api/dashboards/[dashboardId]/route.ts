import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import {
  getDashboard,
  updateDashboard,
  deleteDashboard,
} from "@/queries/dashboards";

/**
 * GET /api/dashboards/[dashboardId] — get a single dashboard.
 */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ dashboardId: string }> }
) {
  const { dashboardId } = await params;
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const dashboard = await getDashboard(dashboardId, session.userId);
    if (!dashboard) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }
    return NextResponse.json(dashboard);
  } catch (error) {
    console.error("Get dashboard error:", error);
    return NextResponse.json(
      { error: "Failed to get dashboard" },
      { status: 500 }
    );
  }
}

/**
 * PATCH /api/dashboards/[dashboardId] — update a dashboard.
 * Body: { name?, description?, config? }
 */
export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ dashboardId: string }> }
) {
  const { dashboardId } = await params;
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const body = await request.json();
    const dashboard = await updateDashboard(dashboardId, session.userId, body);
    if (!dashboard) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }
    return NextResponse.json(dashboard);
  } catch (error) {
    console.error("Update dashboard error:", error);
    return NextResponse.json(
      { error: "Failed to update dashboard" },
      { status: 500 }
    );
  }
}

/**
 * DELETE /api/dashboards/[dashboardId] — delete a dashboard.
 */
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ dashboardId: string }> }
) {
  const { dashboardId } = await params;
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const deleted = await deleteDashboard(dashboardId, session.userId);
    if (!deleted) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }
    return NextResponse.json({ ok: true });
  } catch (error) {
    console.error("Delete dashboard error:", error);
    return NextResponse.json(
      { error: "Failed to delete dashboard" },
      { status: 500 }
    );
  }
}
