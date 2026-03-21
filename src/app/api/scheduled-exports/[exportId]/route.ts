import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import {
  getScheduledExport,
  updateScheduledExport,
  deleteScheduledExport,
} from "@/queries/scheduled-exports";

/**
 * GET /api/scheduled-exports/[exportId] — get a single scheduled export.
 */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ exportId: string }> }
) {
  const { exportId } = await params;
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const result = await getScheduledExport(exportId, session.userId);
    if (!result) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }
    return NextResponse.json(result);
  } catch (error) {
    console.error("Get scheduled export error:", error);
    return NextResponse.json(
      { error: "Failed to get scheduled export" },
      { status: 500 }
    );
  }
}

/**
 * PATCH /api/scheduled-exports/[exportId] — update a scheduled export.
 * Body: { name?, description?, config?: Partial<ScheduledExportConfig> }
 */
export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ exportId: string }> }
) {
  const { exportId } = await params;
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const body = await request.json();
    const result = await updateScheduledExport(exportId, session.userId, body);
    if (!result) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }
    return NextResponse.json(result);
  } catch (error) {
    console.error("Update scheduled export error:", error);
    return NextResponse.json(
      { error: "Failed to update scheduled export" },
      { status: 500 }
    );
  }
}

/**
 * DELETE /api/scheduled-exports/[exportId] — delete a scheduled export.
 */
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ exportId: string }> }
) {
  const { exportId } = await params;
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const deleted = await deleteScheduledExport(exportId, session.userId);
    if (!deleted) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }
    return NextResponse.json({ ok: true });
  } catch (error) {
    console.error("Delete scheduled export error:", error);
    return NextResponse.json(
      { error: "Failed to delete scheduled export" },
      { status: 500 }
    );
  }
}
