"""API key management endpoint methods for the Mantecato Python SDK.

Provides create, list, and delete operations for API keys.  API keys are
stored as ``report`` rows with ``type='api-key'`` and use SHA-256 hashed
tokens.  The raw ``mtk_...`` token is only returned once at creation time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mantecato_client._client import MantecatoClient


class ApiKeysEndpoints:
    """API key management methods.

    Accessed via ``client.api_keys`` on a :class:`MantecatoClient` instance.

    Example::

        result = client.api_keys.create(name="CI/CD key", scopes=["read"])
        print(result["key"])  # mtk_... -- only shown once!
    """

    def __init__(self, client: MantecatoClient) -> None:
        """Initialize with a reference to the parent client.

        Args:
            client: The :class:`MantecatoClient` instance that owns this
                endpoint group.
        """
        self._client = client

    def list(self) -> dict[str, Any]:
        """List all API keys for the authenticated user.

        Returns:
            Dict with an ``api_keys`` key containing a list of API key
            metadata dicts (name, created_at, scopes -- but NOT the raw
            token, which is only shown at creation time).
        """
        return self._client._get("/api/api-keys/")

    def create(self, *, name: str, scopes: list[str] | None = None) -> dict[str, Any]:
        """Create a new API key.

        The raw ``mtk_...`` token is returned in the response and is only
        available at creation time.  It cannot be retrieved later.

        Args:
            name: Human-readable name for the key (e.g. ``"CI/CD key"``).
            scopes: Optional list of permission scopes (e.g. ``["read"]``).
                If ``None``, the key inherits default scopes.

        Returns:
            Dict including ``key`` (the raw ``mtk_...`` token), ``id``,
            ``name``, ``scopes``, ``created_at``.

        Raises:
            ValidationError: If the name is missing or invalid.
        """
        body: dict[str, Any] = {"name": name}
        if scopes is not None:
            body["scopes"] = scopes
        return self._client._post("/api/api-keys/create/", body)

    def delete(self, key_id: str) -> dict[str, Any]:
        """Delete (revoke) an API key by ID.

        Args:
            key_id: UUID of the API key to revoke.

        Returns:
            Confirmation dict (typically ``{"ok": True}``).

        Raises:
            NotFoundError: If no API key exists with the given ID.
        """
        return self._client._post(f"/api/api-keys/{key_id}/delete/")
