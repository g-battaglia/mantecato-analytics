/**
 * API key CRUD operations.
 *
 * API keys are stored in the `report` table with type = 'api-key'.
 * The `parameters` JSON field holds:
 *   - keyHash:   SHA-256 hex hash of the full key (mtk_...)
 *   - prefix:    first 8 chars of the key for display (mtk_xxxx)
 *   - scopes:    string[] of allowed scopes (currently: ["read", "write"])
 *   - createdAt: ISO timestamp of key creation
 *   - lastUsedAt: ISO timestamp of last use (nullable)
 *
 * The full key is only shown once at creation time.
 * We never store the raw key — only its hash.
 */
import { randomBytes, createHash } from "crypto";
import { rawQuery } from "@/lib/queries";

// ── Types ───────────────────────────────────────────────────────────────────

export interface ApiKeyRecord {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  createdAt: string;
  lastUsedAt: string | null;
}

export interface ApiKeyCreateResult {
  id: string;
  name: string;
  key: string; // full key — shown only once
  prefix: string;
  scopes: string[];
  createdAt: string;
}

interface ReportRow {
  report_id: string;
  name: string;
  parameters: string | Record<string, unknown>;
}

// ── Constants ───────────────────────────────────────────────────────────────

const API_KEY_TYPE = "api-key";
// Use a fixed websiteId placeholder (report table requires it)
const PLACEHOLDER_WEBSITE_ID = "00000000-0000-0000-0000-000000000000";

// ── Helpers ─────────────────────────────────────────────────────────────────

function hashKey(key: string): string {
  return createHash("sha256").update(key).digest("hex");
}

function generateKey(): string {
  const bytes = randomBytes(32);
  return `mtk_${bytes.toString("base64url")}`;
}

function parseParams(params: string | Record<string, unknown>): Record<string, unknown> {
  if (typeof params === "string") return JSON.parse(params);
  return params;
}

// ── CRUD ────────────────────────────────────────────────────────────────────

/**
 * List all API keys for a user (without exposing the hash).
 */
export async function listApiKeys(userId: string): Promise<ApiKeyRecord[]> {
  const rows = await rawQuery<ReportRow>(
    `SELECT report_id, name, parameters
     FROM report
     WHERE user_id = {{userId::uuid}}
       AND type = '${API_KEY_TYPE}'
     ORDER BY created_at DESC`,
    { userId }
  );

  return rows.map((r) => {
    const p = parseParams(r.parameters);
    return {
      id: r.report_id,
      name: r.name,
      prefix: (p.prefix as string) || "mtk_???",
      scopes: (p.scopes as string[]) || ["read"],
      createdAt: (p.createdAt as string) || "",
      lastUsedAt: (p.lastUsedAt as string) || null,
    };
  });
}

/**
 * Create a new API key. Returns the full key (shown only once).
 */
export async function createApiKey(
  userId: string,
  name: string,
  scopes: string[] = ["read", "write"]
): Promise<ApiKeyCreateResult> {
  const key = generateKey();
  const keyHash = hashKey(key);
  const prefix = key.slice(0, 12) + "...";
  const now = new Date().toISOString();
  const id = crypto.randomUUID();

  const params = JSON.stringify({
    keyHash,
    prefix,
    scopes,
    createdAt: now,
    lastUsedAt: null,
  });

  await rawQuery(
    `INSERT INTO report (report_id, user_id, website_id, type, name, description, parameters)
     VALUES ({{id::uuid}}, {{userId::uuid}}, {{websiteId::uuid}}, {{type}}, {{name}}, {{description}}, {{params}}::jsonb)`,
    {
      id,
      userId,
      websiteId: PLACEHOLDER_WEBSITE_ID,
      type: API_KEY_TYPE,
      name,
      description: "",
      params,
    }
  );

  return { id, name, key, prefix, scopes, createdAt: now };
}

/**
 * Delete an API key by ID (only if owned by the user).
 */
export async function deleteApiKey(
  id: string,
  userId: string
): Promise<boolean> {
  const result = await rawQuery<{ count: bigint }>(
    `WITH deleted AS (
       DELETE FROM report
       WHERE report_id = {{id::uuid}}
         AND user_id = {{userId::uuid}}
         AND type = '${API_KEY_TYPE}'
       RETURNING 1
     )
     SELECT COUNT(*)::bigint AS count FROM deleted`,
    { id, userId }
  );
  return Number(result[0]?.count ?? 0) > 0;
}

/**
 * Validate an API key. Returns the userId if valid, null otherwise.
 * Also updates lastUsedAt.
 */
export async function validateApiKey(
  key: string
): Promise<{ userId: string; scopes: string[] } | null> {
  if (!key.startsWith("mtk_")) return null;

  const keyHash = hashKey(key);

  // Find the report row that contains this hash
  const rows = await rawQuery<{
    report_id: string;
    user_id: string;
    parameters: string | Record<string, unknown>;
  }>(
    `SELECT report_id, user_id, parameters
     FROM report
     WHERE type = '${API_KEY_TYPE}'`,
    {}
  );

  for (const row of rows) {
    const p = parseParams(row.parameters);
    if (p.keyHash === keyHash) {
      // Update lastUsedAt (fire and forget)
      const now = new Date().toISOString();
      const updatedParams = { ...p, lastUsedAt: now };
      rawQuery(
        `UPDATE report
         SET parameters = {{params}}::jsonb, updated_at = NOW()
         WHERE report_id = {{reportId::uuid}}`,
        { params: JSON.stringify(updatedParams), reportId: row.report_id }
      ).catch(() => {});

      return {
        userId: row.user_id,
        scopes: (p.scopes as string[]) || ["read"],
      };
    }
  }

  return null;
}
