import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import {
  getSavedView,
  updateSavedView,
  deleteSavedView,
} from "@/queries/saved-views";
import type { SavedViewConfig } from "@/queries/saved-views";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ siteId: string; viewId: string }> }
) {
  const { viewId } = await params;
  const session = await getSession();
  if (!session)
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  try {
    const view = await getSavedView(viewId, session.userId);
    if (!view)
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    return NextResponse.json(view);
  } catch (error) {
    console.error("Get saved view error:", error);
    return NextResponse.json(
      { error: "Failed to fetch saved view" },
      { status: 500 }
    );
  }
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ siteId: string; viewId: string }> }
) {
  const { viewId } = await params;
  const session = await getSession();
  if (!session)
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  try {
    const body = await request.json();
    const updates: {
      name?: string;
      description?: string;
      config?: SavedViewConfig;
    } = {};
    if (body.name !== undefined) updates.name = body.name;
    if (body.description !== undefined) updates.description = body.description;
    if (body.config !== undefined) updates.config = body.config;

    const view = await updateSavedView(viewId, session.userId, updates);
    if (!view)
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    return NextResponse.json(view);
  } catch (error) {
    console.error("Update saved view error:", error);
    return NextResponse.json(
      { error: "Failed to update saved view" },
      { status: 500 }
    );
  }
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ siteId: string; viewId: string }> }
) {
  const { viewId } = await params;
  const session = await getSession();
  if (!session)
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  try {
    const deleted = await deleteSavedView(viewId, session.userId);
    if (!deleted)
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    return NextResponse.json({ ok: true });
  } catch (error) {
    console.error("Delete saved view error:", error);
    return NextResponse.json(
      { error: "Failed to delete saved view" },
      { status: 500 }
    );
  }
}
