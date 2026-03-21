import { NextRequest, NextResponse } from "next/server";
import { getSession, canAccessWebsite } from "@/lib/auth";
import { listSavedViews, createSavedView } from "@/queries/saved-views";
import type { SavedViewConfig } from "@/queries/saved-views";

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
    const views = await listSavedViews(session.userId, siteId);
    return NextResponse.json(views);
  } catch (error) {
    console.error("Saved views list error:", error);
    return NextResponse.json(
      { error: "Failed to fetch saved views" },
      { status: 500 }
    );
  }
}

export async function POST(
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
    const body = await request.json();
    const { name, description, config } = body as {
      name: string;
      description?: string;
      config: SavedViewConfig;
    };

    if (!name || !config) {
      return NextResponse.json(
        { error: "Name and config are required" },
        { status: 400 }
      );
    }

    const view = await createSavedView(
      session.userId,
      siteId,
      name,
      description || "",
      config
    );
    return NextResponse.json(view, { status: 201 });
  } catch (error) {
    console.error("Create saved view error:", error);
    return NextResponse.json(
      { error: "Failed to create saved view" },
      { status: 500 }
    );
  }
}
