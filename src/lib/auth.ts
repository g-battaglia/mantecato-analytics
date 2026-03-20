import { compare } from "bcryptjs";
import { SignJWT, jwtVerify } from "jose";
import { cookies } from "next/headers";
import { prisma } from "./prisma";

const SECRET = new TextEncoder().encode(
  process.env.SESSION_SECRET || "mantecato-default-secret"
);

const COOKIE_NAME = "mantecato-session";
const COOKIE_MAX_AGE = 60 * 60 * 24 * 7; // 7 days

export interface SessionPayload {
  userId: string;
  username: string;
  role: string;
}

/**
 * Verify a user's password against the bcrypt hash in the database.
 */
export async function verifyCredentials(
  username: string,
  password: string
): Promise<SessionPayload | null> {
  const user = await prisma.user.findFirst({
    where: { username },
  });

  if (!user) return null;

  const valid = await compare(password, user.password);
  if (!valid) return null;

  return {
    userId: user.user_id,
    username: user.username,
    role: user.role,
  };
}

/**
 * Create a JWT session token.
 */
export async function createSessionToken(
  payload: SessionPayload
): Promise<string> {
  return new SignJWT(payload as unknown as Record<string, unknown>)
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(`${COOKIE_MAX_AGE}s`)
    .sign(SECRET);
}

/**
 * Verify and decode a session token.
 */
export async function verifySessionToken(
  token: string
): Promise<SessionPayload | null> {
  try {
    const { payload } = await jwtVerify(token, SECRET);
    return payload as unknown as SessionPayload;
  } catch {
    return null;
  }
}

/**
 * Get the current session from cookies (server-side).
 */
export async function getSession(): Promise<SessionPayload | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get(COOKIE_NAME)?.value;
  if (!token) return null;
  return verifySessionToken(token);
}

/**
 * Set the session cookie (used in API route after login).
 */
export async function setSessionCookie(token: string): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.set(COOKIE_NAME, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: COOKIE_MAX_AGE,
    path: "/",
  });
}

/**
 * Clear the session cookie (logout).
 */
export async function clearSessionCookie(): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.delete(COOKIE_NAME);
}

/**
 * Get websites the current user has access to.
 */
export async function getUserWebsites(userId: string, role: string) {
  if (role === "admin") {
    return prisma.website.findMany({
      where: { deleted_at: null },
      orderBy: { name: "asc" },
      select: { website_id: true, name: true, domain: true, shareId: true },
    });
  }

  // Get websites owned by user + websites in user's teams
  const teamUsers = await prisma.teamUser.findMany({
    where: { userId },
    select: { teamId: true },
  });

  const teamIds = teamUsers.map((tu: { teamId: string }) => tu.teamId);

  return prisma.website.findMany({
    where: {
      deleted_at: null,
      OR: [{ userId }, ...(teamIds.length > 0 ? [{ teamId: { in: teamIds } }] : [])],
    },
    orderBy: { name: "asc" },
    select: { website_id: true, name: true, domain: true, shareId: true },
  });
}

/**
 * Check if a user has access to a specific website.
 */
export async function canAccessWebsite(
  userId: string,
  role: string,
  websiteId: string
): Promise<boolean> {
  if (role === "admin") return true;

  const website = await prisma.website.findFirst({
    where: {
      website_id: websiteId,
      deleted_at: null,
    },
    select: { userId: true, teamId: true },
  });

  if (!website) return false;
  if (website.userId === userId) return true;

  if (website.teamId) {
    const teamUser = await prisma.teamUser.findFirst({
      where: { teamId: website.teamId, userId },
    });
    if (teamUser) return true;
  }

  return false;
}
