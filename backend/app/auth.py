"""
Authentication module — JWT HS256 sessions via python-jose, bcrypt password
verification (direct bcrypt library), and user/website access-control helpers.

Cross-compatible with the existing jose (JS) tokens: same algorithm (HS256),
same secret, same payload shape.

NOTE: We use the bcrypt library directly instead of passlib because passlib is
unmaintained and incompatible with bcrypt >= 4.1 (bcrypt removed __about__
module causing AttributeError). The JS side uses bcryptjs which produces
standard $2b$ hashes fully compatible with the Python bcrypt library.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from .database import raw_query, raw_query_one
from .config import settings

# -- Constants ----------------------------------------------------------------

COOKIE_NAME = "mantecato-session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days in seconds
ALGORITHM = "HS256"

# -- Password hashing ---------------------------------------------------------


def _hash_password(password: str) -> str:
    """Hash a password using bcrypt. Returns a UTF-8 decoded hash string."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash string."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# -- JWT helpers --------------------------------------------------------------


def create_session_token(payload: dict[str, Any]) -> str:
    """Create a JWT session token compatible with the JS jose implementation."""
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            **payload,
            "iat": now,
            "exp": now.timestamp() + COOKIE_MAX_AGE,
        },
        settings.SESSION_SECRET,
        algorithm=ALGORITHM,
    )


def verify_session_token(token: str) -> dict[str, Any] | None:
    """Verify and decode a JWT session token. Returns payload or None."""
    try:
        payload = jwt.decode(
            token,
            settings.SESSION_SECRET,
            algorithms=[ALGORITHM],
        )
        return payload
    except JWTError:
        return None


# -- Credential verification --------------------------------------------------


async def verify_credentials(username: str, password: str) -> dict[str, Any] | None:
    """
    Verify a user's password against the bcrypt hash stored in the database.
    Returns a session payload dict or None on failure.
    """
    row = await raw_query_one(
        'SELECT user_id, username, role, password FROM "user" WHERE username = {{username}}',
        {"username": username},
    )
    if not row:
        return None

    if not _verify_password(password, row["password"]):
        return None

    # Convert UUID to string so the JWT payload is JSON-serializable
    return {
        "userId": str(row["user_id"]),
        "username": row["username"],
        "role": row["role"],
    }


# -- Website access control ---------------------------------------------------


def _website_row(r: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw DB row (snake_case keys) to the camelCase API shape."""
    return {
        "websiteId": str(r["website_id"]),
        "name": r["name"],
        "domain": r["domain"],
        "shareId": r.get("share_id"),
    }


async def get_user_websites(user_id: str, role: str) -> list[dict[str, Any]]:
    """
    Get websites the current user has access to.
    Admin sees all non-deleted websites; regular users see owned + team websites.
    """
    # SQL column names are snake_case (actual DB columns), not camelCase Prisma fields
    if role == "admin":
        rows = await raw_query(
            """SELECT website_id, name, domain, share_id
               FROM website
               WHERE deleted_at IS NULL
               ORDER BY name ASC""",
            {},
        )
        return [_website_row(r) for r in rows]

    # Get team IDs for this user
    team_rows = await raw_query(
        "SELECT team_id FROM team_user WHERE user_id = {{userId::uuid}}",
        {"userId": user_id},
    )
    team_ids = [r["team_id"] for r in team_rows]

    if team_ids:
        # Build parameterised placeholders for the IN clause
        placeholders = ", ".join(
            f"{{{{teamId_{i}::uuid}}}}" for i in range(len(team_ids))
        )
        sql = f"""
            SELECT website_id, name, domain, share_id
            FROM website
            WHERE deleted_at IS NULL
              AND (user_id = {{{{userId::uuid}}}}
                   OR team_id IN ({placeholders}))
            ORDER BY name ASC
        """
        params: dict[str, Any] = {"userId": user_id}
        for i, tid in enumerate(team_ids):
            params[f"teamId_{i}"] = tid
        rows = await raw_query(sql, params)
        return [_website_row(r) for r in rows]

    # No teams — only owned websites
    rows = await raw_query(
        """SELECT website_id, name, domain, share_id
           FROM website
           WHERE deleted_at IS NULL
             AND user_id = {{userId::uuid}}
           ORDER BY name ASC""",
        {"userId": user_id},
    )
    return [_website_row(r) for r in rows]


async def can_access_website(user_id: str, role: str, website_id: str) -> bool:
    """Check whether a user has access to a specific website."""
    if role == "admin":
        return True

    website = await raw_query_one(
        """SELECT user_id, team_id
           FROM website
           WHERE website_id = {{websiteId::uuid}}
             AND deleted_at IS NULL""",
        {"websiteId": website_id},
    )
    if not website:
        return False

    # Owner check
    if website["user_id"] == user_id:
        return True

    # Team membership check
    if website.get("team_id"):
        member = await raw_query_one(
            "SELECT 1 AS ok FROM team_user WHERE team_id = {{teamId::uuid}} AND user_id = {{userId::uuid}}",
            {"teamId": website["team_id"], "userId": user_id},
        )
        if member:
            return True

    return False
