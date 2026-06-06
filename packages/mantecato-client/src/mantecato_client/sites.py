"""Site (tracked website) endpoint methods for the Mantecato Python SDK.

Provides read-only access to the list of tracked websites the authenticated
API key has access to.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mantecato_client._client import MantecatoClient


class SitesEndpoints:
    """Tracked website listing methods.

    Accessed via ``client.sites`` on a :class:`MantecatoClient` instance.

    Example::

        sites = client.sites.list()
        for site in sites["sites"]:
            print(site["name"], site["domain"])
    """

    def __init__(self, client: MantecatoClient) -> None:
        """Initialize with a reference to the parent client.

        Args:
            client: The :class:`MantecatoClient` instance that owns this
                endpoint group.
        """
        self._client = client

    def list(self) -> dict[str, Any]:
        """List all tracked websites accessible to the authenticated API key.

        Returns:
            Dict with a ``sites`` key containing a list of website dicts,
            each with ``id`` (UUID), ``name``, and ``domain`` keys.
        """
        return self._client._get("/api/sites/")
