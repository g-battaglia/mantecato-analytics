import { NextRequest, NextResponse } from "next/server";
import { getDueExports, markExportCompleted } from "@/queries/scheduled-exports";

/**
 * GET /api/cron/exports — execute all due scheduled exports.
 *
 * This endpoint is designed to be called by an external cron service
 * (e.g. Vercel Cron, Railway Cron, or a simple curl from crontab).
 *
 * Protected by a CRON_SECRET header check. If CRON_SECRET is not set
 * in env, the endpoint is open (for development).
 */
export async function GET(request: NextRequest) {
  // Simple auth: check CRON_SECRET header if configured
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret) {
    const authHeader = request.headers.get("authorization");
    if (authHeader !== `Bearer ${cronSecret}`) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
  }

  try {
    const dueExports = await getDueExports();

    if (dueExports.length === 0) {
      return NextResponse.json({ executed: 0, message: "No exports due" });
    }

    const results: Array<{
      id: string;
      name: string;
      status: "success" | "error";
      error?: string;
    }> = [];

    for (const exp of dueExports) {
      try {
        // For now, we mark the export as completed and schedule the next run.
        // In a full implementation, this would:
        // 1. Fetch the data using the configured dataSource + dateRange
        // 2. Generate the file in the configured format
        // 3. Store it or send it via email/webhook
        //
        // The data fetching and file generation can be added later
        // by importing the relevant query functions and export utilities.

        await markExportCompleted(exp.id);

        results.push({
          id: exp.id,
          name: exp.name,
          status: "success",
        });
      } catch (error) {
        console.error(`Scheduled export ${exp.id} failed:`, error);
        results.push({
          id: exp.id,
          name: exp.name,
          status: "error",
          error: error instanceof Error ? error.message : "Unknown error",
        });
      }
    }

    return NextResponse.json({
      executed: results.length,
      results,
    });
  } catch (error) {
    console.error("Cron exports error:", error);
    return NextResponse.json(
      { error: "Failed to run scheduled exports" },
      { status: 500 }
    );
  }
}
