import { NextResponse } from "next/server";
import { getSession, getUserWebsites } from "@/lib/auth";

export async function GET() {
  const session = await getSession();

  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const websites = await getUserWebsites(session.userId, session.role);
  return NextResponse.json(websites);
}
