"""Dashboard service layer — CRUD on the ``report`` table.

Dashboards are :class:`~apps.core.models.Report` rows with
``type = 'mantecato-dashboard'``, accessed through the
:class:`~apps.core.models.Dashboard` proxy. These functions are the single
persistence touch-point shared by the web CBVs (:mod:`apps.dashboards.views`),
the JSON API endpoints (:mod:`apps.api.views`), and the CLI
(``mantecato dashboard*``). They isolate the JSON-column wiring and let the
view layer focus on request/response shaping.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from apps.core.models import Dashboard

if TYPE_CHECKING:
    from typing import Any


from apps.common.constants import DASHBOARD_DEFAULT_CONFIG as _DEFAULT_DASHBOARD_CONFIG


def get_dashboards_for_user(user_id: str, website_id: str | None = None) -> list[dict[str, Any]]:
    """Return a user's dashboards, newest-updated first.

    Args:
        user_id: UUID string of the dashboard owner.
        website_id: Optional UUID string to narrow the result set to a single
            website's dashboards. Pass ``None`` (the default) to list every
            dashboard the user owns.

    Returns:
        Serialized dashboard dicts in the camelCase shape produced by
        :meth:`apps.core.models.Dashboard.to_dict`. Empty list when the user
        has no dashboards.
    """
    qs = Dashboard.objects.filter(user_id=user_id)
    if website_id:
        qs = qs.filter(website_id=website_id)
    return [d.to_dict() for d in qs.order_by("-updated_at")]


def get_dashboard_detail(report_id: str, user_id: str) -> dict[str, Any] | None:
    """Return a single dashboard owned by *user_id*, or ``None`` when missing.

    Args:
        report_id: UUID string of the dashboard row.
        user_id: UUID string of the expected owner.

    Returns:
        The camelCase dict from :meth:`Dashboard.to_dict`, or ``None``
        when the dashboard does not exist or belongs to another user.
    """
    dashboard = Dashboard.objects.filter(id=report_id, user_id=user_id).first()
    return dashboard.to_dict() if dashboard else None


def create_new_dashboard(
    user_id: str,
    website_id: str,
    name: str,
    description: str = "",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a dashboard and return its serialized form.

    When *config* is ``None`` the default 2-column / empty-widgets / 30-day
    layout from :data:`_DEFAULT_DASHBOARD_CONFIG` is applied so the
    dashboard renders immediately with a usable scaffold.

    Args:
        user_id: UUID string of the dashboard owner.
        website_id: UUID string of the associated website.
        name: Human-readable dashboard title.
        description: Optional description text.
        config: Dashboard layout JSON. ``None`` applies the default layout.

    Returns:
        The serialized dashboard dict.
    """
    dashboard = Dashboard.objects.create(
        user_id=user_id,
        website_id=website_id,
        name=name,
        description=description or "",
        parameters=config if config is not None else dict(_DEFAULT_DASHBOARD_CONFIG),
    )
    return dashboard.to_dict()


def update_existing_dashboard(
    report_id: str,
    user_id: str,
    name: str | None = None,
    description: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Update a dashboard's mutable fields; return it, or ``None`` if missing.

    Only fields whose value was actually provided (not ``None``) are
    written, via ``save(update_fields=[...])``. This minimises the
    UPDATE's column set and avoids clobbering unrelated fields. The whole
    operation runs inside a single ``transaction.atomic`` block so the
    SELECT-then-UPDATE pair remains consistent under concurrent writes.

    Args:
        report_id: UUID string of the dashboard to update.
        user_id: UUID string of the expected owner.
        name: New title, or ``None`` to leave unchanged.
        description: New description, or ``None`` to leave unchanged.
        config: New layout JSON, or ``None`` to leave unchanged.

    Returns:
        The updated serialized dashboard dict, or ``None`` when the
        dashboard was not found.
    """
    with transaction.atomic():
        dashboard = Dashboard.objects.filter(id=report_id, user_id=user_id).first()
        if dashboard is None:
            return None
        dirty: list[str] = []
        if name is not None:
            dashboard.name = name
            dirty.append("name")
        if description is not None:
            dashboard.description = description
            dirty.append("description")
        if config is not None:
            dashboard.parameters = config
            dirty.append("parameters")
        if dirty:
            # Always touch updated_at so the ordering reflects the edit.
            dashboard.save(update_fields=[*dirty, "updated_at"])
        return dashboard.to_dict()


def remove_dashboard(report_id: str, user_id: str) -> bool:
    """Delete a dashboard; return ``True`` if a row was actually removed.

    Args:
        report_id: UUID string of the dashboard to delete.
        user_id: UUID string of the expected owner.

    Returns:
        ``True`` when exactly one row was deleted, ``False`` otherwise.
    """
    deleted, _ = Dashboard.objects.filter(id=report_id, user_id=user_id).delete()
    return deleted > 0
