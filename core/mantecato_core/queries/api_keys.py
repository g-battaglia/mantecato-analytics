"""
API key CRUD operations.

API keys are stored in the `report` table with type = 'api-key'.
The `parameters` JSONB column holds:
  - keyHash:   SHA-256 hex hash of the full key (mtk_...)
  - prefix:    first 12 chars of the key + "..." for display
  - scopes:    list of allowed scopes (e.g., ["read", "write"])
  - createdAt: ISO timestamp of key creation
  - lastUsedAt: ISO timestamp of last use (nullable)

The full key is only shown once at creation time.
We never store the raw key — only its hash.
SQL queries ported verbatim from TypeScript rawQuery calls.
"""

import base64
import hashlib
import json
import os
import uuid
from typing import Any

from mantecato_core.database import raw_query


API_KEY_TYPE = "api-key"
PLACEHOLDER_WEBSITE_ID = "00000000-0000-0000-0000-000000000000"


def hash_key(key: str) -> str:
    """SHA-256 hex hash of the API key."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_key() -> str:
    """Generate a new API key with mtk_ prefix."""
    random_bytes = os.urandom(32)
    return f"mtk_{base64.urlsafe_b64encode(random_bytes).decode().rstrip('=')}"


def _parse_params(params: Any) -> dict[str, Any]:
    """Parse parameters from either a string or dict."""
    if isinstance(params, str):
        return json.loads(params)
    return params or {}


async def list_api_keys(user_id: str) -> list[dict[str, Any]]:
    """List all API keys for a user (without exposing the hash)."""
    rows = await raw_query(
        """SELECT report_id, name, parameters
           FROM report
           WHERE user_id = {{userId::uuid}}
             AND type = 'api-key'
           ORDER BY created_at DESC""",
        {"userId": user_id},
    )

    result = []
    for r in rows:
        p = _parse_params(r.get("parameters"))
        result.append(
            {
                "id": r["report_id"],
                "name": r.get("name", ""),
                "prefix": p.get("prefix", "mtk_???"),
                "scopes": p.get("scopes", ["read"]),
                "createdAt": p.get("createdAt", ""),
                "lastUsedAt": p.get("lastUsedAt"),
            }
        )
    return result


async def create_api_key(
    user_id: str,
    name: str,
    scopes: list[str] | None = None,
) -> dict[str, Any]:
    """Create a new API key. Returns the full key (shown only once)."""
    if scopes is None:
        scopes = ["read", "write"]

    key = generate_key()
    key_hash = hash_key(key)
    prefix = key[:12] + "..."
    now = __import__("datetime").datetime.utcnow().isoformat()
    report_id = str(uuid.uuid4())

    params = json.dumps(
        {
            "keyHash": key_hash,
            "prefix": prefix,
            "scopes": scopes,
            "createdAt": now,
            "lastUsedAt": None,
        }
    )

    await raw_query(
        """INSERT INTO report (report_id, user_id, website_id, type, name, description, parameters)
           VALUES ({{id::uuid}}, {{userId::uuid}}, {{websiteId::uuid}}, {{type}}, {{name}}, {{description}}, {{params}}::jsonb)""",
        {
            "id": report_id,
            "userId": user_id,
            "websiteId": PLACEHOLDER_WEBSITE_ID,
            "type": API_KEY_TYPE,
            "name": name,
            "description": "",
            "params": params,
        },
    )

    return {
        "id": report_id,
        "name": name,
        "key": key,
        "prefix": prefix,
        "scopes": scopes,
        "createdAt": now,
    }


async def delete_api_key(key_id: str, user_id: str) -> bool:
    """Delete an API key by ID (only if owned by the user)."""
    rows = await raw_query(
        """WITH deleted AS (
             DELETE FROM report
             WHERE report_id = {{id::uuid}}
               AND user_id = {{userId::uuid}}
               AND type = 'api-key'
             RETURNING 1
           )
           SELECT COUNT(*)::bigint AS count FROM deleted""",
        {"id": key_id, "userId": user_id},
    )
    return int(rows[0].get("count", 0)) > 0 if rows else False


async def validate_api_key(key: str) -> dict[str, Any] | None:
    """
    Validate an API key. Returns {userId, scopes} if valid, None otherwise.
    Also updates lastUsedAt (fire and forget).
    """
    if not key.startswith("mtk_"):
        return None

    key_hash = hash_key(key)

    rows = await raw_query(
        """SELECT report_id, user_id, parameters
           FROM report
           WHERE type = 'api-key'
             AND parameters->>'keyHash' = {{keyHash}}""",
        {"keyHash": key_hash},
    )

    if not rows:
        return None

    row = rows[0]
    p = _parse_params(row.get("parameters"))

    # Update lastUsedAt (fire and forget — don't await)
    import datetime as _dt

    now = _dt.datetime.utcnow().isoformat()
    updated_params = {**p, "lastUsedAt": now}
    # Fire-and-forget: schedule but don't block
    import asyncio

    async def _update_last_used() -> None:
        await raw_query(
            """UPDATE report
               SET parameters = {{params}}::jsonb, updated_at = NOW()
               WHERE report_id = {{reportId::uuid}}""",
            {"params": json.dumps(updated_params), "reportId": row["report_id"]},
        )

    asyncio.ensure_future(_update_last_used())

    return {
        "userId": row["user_id"],
        "scopes": p.get("scopes", ["read"]),
    }
