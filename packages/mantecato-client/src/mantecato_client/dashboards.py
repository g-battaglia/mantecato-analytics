"""Dashboard CRUD endpoint methods for the Mantecato Python SDK.

Provides create, read, update, and delete operations for custom analytics
dashboards.  Dashboards are stored as ``report`` rows with
``type='mantecato-dashboard'`` and hold a JSON config defining which
widgets to display.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mantecato_client._client import MantecatoClient


class DashboardsEndpoints:
    """Custom dashboard CRUD methods.

    Accessed via ``client.dashboards`` on a :class:`MantecatoClient` instance.
    """

    def __init__(self, client: MantecatoClient) -> None:
        """Initialize with a reference to the parent client.

        Args:
            client: The :class:`MantecatoClient` instance that owns this
                endpoint group.
        """
        self._client = client

    def list(self, *, website_id: str | None = None) -> dict[str, Any]:
        """List all dashboards, optionally filtered by website.

        Args:
            website_id: Optional UUID to filter dashboards by website.
                If ``None``, returns dashboards across all websites.

        Returns:
            Dict with a ``dashboards`` key containing a list of dashboard dicts.
        """
        params: dict[str, Any] = {}
        if website_id:
            params["website"] = website_id
        return self._client._get("/api/dashboards/", params or None)

    def get(self, dashboard_id: str) -> dict[str, Any]:
        """Retrieve a single dashboard by ID.

        Args:
            dashboard_id: UUID of the dashboard to retrieve.

        Returns:
            Dashboard dict with keys ``id``, ``name``, ``description``,
            ``config``, ``website_id``, ``created_at``, ``updated_at``.

        Raises:
            NotFoundError: If no dashboard exists with the given ID.
        """
        return self._client._get(f"/api/dashboards/{dashboard_id}/")

    def create(
        self,
        *,
        name: str,
        website_id: str,
        description: str = "",
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new custom dashboard.

        Args:
            name: Display name for the dashboard.
            website_id: UUID of the website this dashboard belongs to.
            description: Optional description text.
            config: Optional JSON-serializable dict defining dashboard
                widgets and layout.

        Returns:
            The created dashboard dict including the new ``id``.

        Raises:
            ValidationError: If required fields are missing or invalid.
        """
        body: dict[str, Any] = {"name": name, "website_id": website_id}
        if description:
            body["description"] = description
        if config is not None:
            body["config"] = config
        return self._client._post("/api/dashboards/create/", body)

    def update(
        self,
        dashboard_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update an existing dashboard.  Only provided fields are changed.

        Args:
            dashboard_id: UUID of the dashboard to update.
            name: New display name (or ``None`` to keep current).
            description: New description (or ``None`` to keep current).
            config: New widget/layout config (or ``None`` to keep current).

        Returns:
            The updated dashboard dict.

        Raises:
            NotFoundError: If no dashboard exists with the given ID.
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if config is not None:
            body["config"] = config
        return self._client._post(f"/api/dashboards/{dashboard_id}/update/", body)

    def delete(self, dashboard_id: str) -> dict[str, Any]:
        """Delete a dashboard by ID.

        Args:
            dashboard_id: UUID of the dashboard to delete.

        Returns:
            Confirmation dict (typically ``{"ok": True}``).

        Raises:
            NotFoundError: If no dashboard exists with the given ID.
        """
        return self._client._post(f"/api/dashboards/{dashboard_id}/delete/")
