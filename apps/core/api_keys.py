"""API-key cryptography and authentication.

API keys are ``report`` rows (``type = 'api-key'``); their SHA-256 hash and
metadata live in the ``parameters`` JSON column. This module holds the
auth-critical, non-CRUD helpers — hashing, key generation, and the
``validate_api_key`` lookup the request middleware runs on every API call.
"""

from __future__ import annotations

import base64
import hashlib
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from apps.core.models import ApiKey

if TYPE_CHECKING:
    from typing import Any


def hash_key(key: str) -> str:
    """Return the SHA-256 hex digest of an API key.

    The hash is stored in ``report.parameters.keyHash`` and used for
    authentication lookups. SHA-256 is one-way -- the raw key cannot be
    recovered from the database.

    Args:
        key: The raw API key string (e.g. ``"mtk_abc..."``).

    Returns:
        A 64-character lowercase hex digest.
    """
    return hashlib.sha256(key.encode()).hexdigest()


def generate_key() -> str:
    """Generate a new random API key with the ``mtk_`` prefix.

    Uses 32 bytes of OS entropy (``os.urandom``), base64url-encoded.
    The ``mtk_`` prefix makes keys visually identifiable in logs and
    config files without revealing their contents.

    Returns:
        A string like ``"mtk_<43 base64url chars>"``.
    """
    return f"mtk_{base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip('=')}"


def validate_api_key(key: str) -> dict[str, Any] | None:
    """Resolve an API key to its owner identity, or ``None`` if invalid.

    Called by :class:`mantecato.middleware.ApiKeyMiddleware` on every
    request carrying an ``Authorization: Bearer mtk_...`` header.

    The lookup hashes the presented key and queries the ``report`` table
    for a matching ``parameters->keyHash``. A successful match also
    refreshes the ``lastUsedAt`` timestamp (touching only the JSON column
    via ``save(update_fields=["parameters"])`` to keep the write cheap).

    Args:
        key: The raw API key string from the Authorization header.

    Returns:
        ``{"userId": "<uuid>", "scopes": ["read", "write", ...]}`` on
        success, or ``None`` when the key is malformed or unknown.
    """
    # Quick reject: keys must carry the mtk_ prefix.
    if not key.startswith("mtk_"):
        return None

    # Look up by hash -- never store or compare raw keys.
    api_key = ApiKey.objects.filter(parameters__keyHash=hash_key(key)).first()
    if api_key is None:
        return None

    # Refresh the last-used timestamp for key lifecycle tracking.
    params = api_key.parameters or {}
    api_key.parameters = {**params, "lastUsedAt": datetime.now(UTC).isoformat()}
    api_key.save(update_fields=["parameters"])

    return {
        "userId": str(api_key.user_id),
        "scopes": params.get("scopes", ["read"]),
    }
