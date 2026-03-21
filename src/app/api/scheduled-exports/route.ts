import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import {
  listScheduledExports,
  createScheduledExport,
  ScheduledExportConfig,
} from "@/queries/scheduled-exports";

/**
 * GET /api/scheduled-exports — list all scheduled exports for the current user.
 */
export async function GET() {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const exports = await listScheduledExports(session.userId);
    return NextResponse.json(exports);
  } catch (error) {
    console.error("List scheduled exports error:", error);
    return NextResponse.json(
      { error: "Failed to list scheduled exports" },
      { status: 500 }
    );
  }
}

/**
 * POST /api/scheduled-exports — create a new scheduled export.
 * Body: { name, description?, config: ScheduledExportConfig }
 */
export async function POST(request: NextRequest) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const body = await request.json();
    const { name, description, config } = body as {
      name: string;
      description?: string;
      config: ScheduledExportConfig;
    };

    if (!name || !config?.websiteId || !config?.dataSource || !config?.format || !config?.schedule) {
      return NextResponse.json(
        { error: "name, config.websiteId, config.dataSource, config.format, and config.schedule are required" },
        { status: 400 }
      );
    }

    const result = await createScheduledExport(
      session.userId,
      name,
      description ?? "",
      config
    );

    return NextResponse.json(result, { status: 201 });
  } catch (error) {
    console.error("Create scheduled export error:", error);
    return NextResponse.json(
      { error: "Failed to create scheduled export" },
      { status: 500 }
    );
  }
}
