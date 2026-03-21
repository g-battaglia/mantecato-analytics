import { NextResponse } from "next/server";
import { readFile } from "fs/promises";
import { join } from "path";

/**
 * Serve the Mantecato tracker script as a JS file.
 *
 * Usage:
 *   <script defer src="https://your-domain.com/api/script" data-website-id="..."></script>
 *
 * The script is read from the pre-built tracker package at build time.
 * Cached aggressively via Cache-Control (immutable content, versioned by build).
 */
export async function GET() {
  try {
    const scriptPath = join(
      process.cwd(),
      "packages",
      "tracker",
      "dist",
      "script.js"
    );
    const script = await readFile(scriptPath, "utf-8");

    return new NextResponse(script, {
      status: 200,
      headers: {
        "Content-Type": "application/javascript; charset=utf-8",
        "Cache-Control": "public, max-age=86400, s-maxage=86400",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "Tracker script not found. Run: npm run build -w @mantecato/tracker" },
      { status: 500 }
    );
  }
}
