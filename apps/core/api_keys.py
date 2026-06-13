"""API-key cryptography and authentication.

API keys are ``report`` rows (``type = 'api-key'``); their SHA-256 hash and
metadata live in the ``parameters`` JSON column. This module holds the
auth-critical, non-CRUD helpers — hashing, key generation, and the
``validate_api_key`` lookup the request middleware runs on every API call.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from django.conf import settings

from apps.core.models import ApiKey

if TYPE_CHECKING:
    from typing import Any

# The permission scopes a key may hold. ``admin`` bypasses per-website
# tenant restrictions, so granting it is gated (see ``settings_app.services``).
VALID_SCOPES: tuple[str, ...] = ("read", "write", "admin")

# How stale ``lastUsedAt`` may be before a successful auth refreshes it. The
# timestamp is informational, so we avoid a row write on every single request
# (which would serialise high-rate callers on one row and amplify WAL writes).
_LAST_USED_REFRESH_S = 60


def hash_key(key: str) -> str:
    """Return a keyed (peppered) digest of an API key.

    Uses HMAC-SHA256 with ``settings.SECRET_KEY`` as the pepper rather than a
    bare SHA-256. The raw key already carries 256 bits of entropy, so brute
    force is infeasible either way; the pepper additionally means that a leaked
    ``report`` table alone is useless to an attacker -- matching a stored hash
    also requires the server secret. The digest is stored in
    ``report.parameters.keyHash`` and used for authentication lookups.

    NOTE: changing the pepper (i.e. rotating ``SECRET_KEY``) invalidates all
    existing keys. Keys created before this scheme (bare SHA-256) will no
    longer validate and must be regenerated.

    Args:
        key: The raw API key string (e.g. ``"mtk_abc..."``).

    Returns:
        A 64-character lowercase hex digest.
    """
    return hmac.new(
        settings.SECRET_KEY.encode(),
        key.encode(),
        hashlib.sha256,
    ).hexdigest()


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

    # Look up by hash -- never store or compare raw keys. The comparison is an
    # indexed equality on a hash of a high-entropy secret, so it does not leak
    # the key via timing; a byte-by-byte ``compare_digest`` is unnecessary here.
    api_key = ApiKey.objects.filter(parameters__keyHash=hash_key(key)).first()
    if api_key is None:
        return None

    # Refresh the last-used timestamp for key lifecycle tracking, but throttle
    # the write: skip it when the timestamp is already fresh so high-rate
    # callers don't serialise on (and rewrite) the same row every request.
    params = api_key.parameters or {}
    now = datetime.now(UTC)
    if _should_refresh_last_used(params.get("lastUsedAt"), now):
        api_key.parameters = {**params, "lastUsedAt": now.isoformat()}
        api_key.save(update_fields=["parameters"])

    return {
        "userId": str(api_key.user_id),
        "scopes": params.get("scopes", ["read"]),
    }


def _should_refresh_last_used(last_used: str | None, now: datetime) -> bool:
    """Return ``True`` when ``lastUsedAt`` is missing or older than the window."""
    if not last_used:
        return True
    try:
        previous = datetime.fromisoformat(last_used)
    except (TypeError, ValueError):
        return True
    return now - previous >= timedelta(seconds=_LAST_USED_REFRESH_S)
