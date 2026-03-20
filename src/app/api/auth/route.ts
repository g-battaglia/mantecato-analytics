import { NextRequest, NextResponse } from "next/server";
import {
  verifyCredentials,
  createSessionToken,
  setSessionCookie,
  clearSessionCookie,
} from "@/lib/auth";

export async function POST(request: NextRequest) {
  try {
    const { username, password } = await request.json();

    if (!username || !password) {
      return NextResponse.json(
        { error: "Username and password are required" },
        { status: 400 }
      );
    }

    const session = await verifyCredentials(username, password);

    if (!session) {
      return NextResponse.json(
        { error: "Invalid username or password" },
        { status: 401 }
      );
    }

    const token = await createSessionToken(session);
    await setSessionCookie(token);

    return NextResponse.json({
      user: {
        userId: session.userId,
        username: session.username,
        role: session.role,
      },
    });
  } catch (error) {
    console.error("Auth error:", error);
    console.error("Auth error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}

export async function DELETE() {
  await clearSessionCookie();
  return NextResponse.json({ success: true });
}
