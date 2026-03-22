import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { listApiKeys, createApiKey, deleteApiKey } from "@/queries/api-keys";

/**
 * GET /api/api-keys — list all API keys for the current user.
 */
export async function GET() {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const keys = await listApiKeys(session.userId);
    return NextResponse.json(keys);
  } catch (error) {
    console.error("List API keys error:", error);
    return NextResponse.json(
      { error: "Failed to list API keys" },
      { status: 500 }
    );
  }
}

/**
 * POST /api/api-keys — create a new API key.
 * Body: { name, scopes? }
 * Returns the full key (shown only once).
 */
export async function POST(request: NextRequest) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const body = await request.json();
    const { name, scopes } = body as {
      name: string;
      scopes?: string[];
    };

    if (!name?.trim()) {
      return NextResponse.json(
        { error: "name is required" },
        { status: 400 }
      );
    }

    const result = await createApiKey(
      session.userId,
      name.trim(),
      scopes || ["read", "write"]
    );

    return NextResponse.json(result, { status: 201 });
  } catch (error) {
    console.error("Create API key error:", error);
    return NextResponse.json(
      { error: "Failed to create API key" },
      { status: 500 }
    );
  }
}

/**
 * DELETE /api/api-keys — delete an API key.
 * Body: { id }
 */
export async function DELETE(request: NextRequest) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const body = await request.json();
    const { id } = body as { id: string };

    if (!id) {
      return NextResponse.json({ error: "id is required" }, { status: 400 });
    }

    const deleted = await deleteApiKey(id, session.userId);
    if (!deleted) {
      return NextResponse.json(
        { error: "API key not found or not owned by you" },
        { status: 404 }
      );
    }

    return NextResponse.json({ deleted: true });
  } catch (error) {
    console.error("Delete API key error:", error);
    return NextResponse.json(
      { error: "Failed to delete API key" },
      { status: 500 }
    );
  }
}
