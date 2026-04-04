"""
Dashboard CRUD operations.

Dashboards are stored in the `report` table with type = 'mantecato-dashboard'.
The `parameters` JSONB column holds the DashboardConfig object:
  {version, columns, widgets[], dateRange}
Converted from Prisma ORM to raw SQL.
"""

import json
import uuid
from datetime import datetime
from typing import Any

from mantecato_core.database import raw_query


DASHBOARD_TYPE = "mantecato-dashboard"


def _report_to_dashboard(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a report row to a dashboard dict."""
    params = row.get("parameters", {})
    if isinstance(params, str):
        params = json.loads(params)

    created_at = row.get("created_at")
    updated_at = row.get("updated_at")

    return {
        "id": row["report_id"],
        "name": row.get("name", ""),
        "description": row.get("description", ""),
        "userId": row.get("user_id", ""),
        "websiteId": row.get("website_id", ""),
        "config": params,
        "createdAt": created_at.isoformat()
        if isinstance(created_at, datetime)
        else datetime.utcnow().isoformat(),
        "updatedAt": updated_at.isoformat()
        if isinstance(updated_at, datetime)
        else datetime.utcnow().isoformat(),
    }


async def list_dashboards(
    user_id: str,
    website_id: str | None = None,
) -> list[dict[str, Any]]:
    """List all dashboards for a user, optionally filtered by website."""
    if website_id:
        rows = await raw_query(
            """SELECT report_id, name, description, user_id, website_id, parameters, created_at, updated_at
               FROM report
               WHERE type = {{type}}
                 AND user_id = {{userId::uuid}}
                 AND website_id = {{websiteId::uuid}}
               ORDER BY updated_at DESC""",
            {"type": DASHBOARD_TYPE, "userId": user_id, "websiteId": website_id},
        )
    else:
        rows = await raw_query(
            """SELECT report_id, name, description, user_id, website_id, parameters, created_at, updated_at
               FROM report
               WHERE type = {{type}}
                 AND user_id = {{userId::uuid}}
               ORDER BY updated_at DESC""",
            {"type": DASHBOARD_TYPE, "userId": user_id},
        )
    return [_report_to_dashboard(r) for r in rows]


async def get_dashboard(report_id: str, user_id: str) -> dict[str, Any] | None:
    """Get a single dashboard by ID."""
    rows = await raw_query(
        """SELECT report_id, name, description, user_id, website_id, parameters, created_at, updated_at
           FROM report
           WHERE report_id = {{reportId::uuid}}
             AND type = {{type}}
             AND user_id = {{userId::uuid}}""",
        {"reportId": report_id, "type": DASHBOARD_TYPE, "userId": user_id},
    )
    return _report_to_dashboard(rows[0]) if rows else None


async def create_dashboard(
    user_id: str,
    website_id: str,
    name: str,
    description: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Create a new dashboard."""
    report_id = str(uuid.uuid4())

    await raw_query(
        """INSERT INTO report (report_id, user_id, website_id, type, name, description, parameters)
           VALUES ({{id::uuid}}, {{userId::uuid}}, {{websiteId::uuid}}, {{type}}, {{name}}, {{description}}, {{params}}::jsonb)""",
        {
            "id": report_id,
            "userId": user_id,
            "websiteId": website_id,
            "type": DASHBOARD_TYPE,
            "name": name,
            "description": description or "",
            "params": json.dumps(config),
        },
    )

    row = await raw_query(
        """SELECT report_id, name, description, user_id, website_id, parameters, created_at, updated_at
           FROM report WHERE report_id = {{id::uuid}}""",
        {"id": report_id},
    )
    return _report_to_dashboard(row[0])


async def update_dashboard(
    report_id: str,
    user_id: str,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    """Update an existing dashboard. Returns the updated dashboard or None if not found."""
    existing = await raw_query(
        """SELECT report_id, name, description, user_id, website_id, parameters, created_at, updated_at
           FROM report
           WHERE report_id = {{reportId::uuid}}
             AND type = {{type}}
             AND user_id = {{userId::uuid}}""",
        {"reportId": report_id, "type": DASHBOARD_TYPE, "userId": user_id},
    )
    if not existing:
        return None

    set_parts: list[str] = []
    params: dict[str, Any] = {
        "reportId": report_id,
        "type": DASHBOARD_TYPE,
        "userId": user_id,
    }

    if "name" in updates and updates["name"] is not None:
        set_parts.append("name = {{name}}")
        params["name"] = updates["name"]

    if "description" in updates and updates["description"] is not None:
        set_parts.append("description = {{description}}")
        params["description"] = updates["description"]

    if "config" in updates and updates["config"] is not None:
        set_parts.append("parameters = {{params}}::jsonb")
        params["params"] = json.dumps(updates["config"])

    if not set_parts:
        return _report_to_dashboard(existing[0])

    set_clause = ", ".join(set_parts)
    rows = await raw_query(
        f"UPDATE report SET {set_clause}, updated_at = NOW() WHERE report_id = {{reportId::uuid}} RETURNING report_id, name, description, user_id, website_id, parameters, created_at, updated_at",
        params,
    )
    return _report_to_dashboard(rows[0])


async def delete_dashboard(report_id: str, user_id: str) -> bool:
    """Delete a dashboard. Returns True if deleted, False if not found."""
    existing = await raw_query(
        """SELECT report_id FROM report
           WHERE report_id = {{reportId::uuid}}
             AND type = {{type}}
             AND user_id = {{userId::uuid}}""",
        {"reportId": report_id, "type": DASHBOARD_TYPE, "userId": user_id},
    )
    if not existing:
        return False

    await raw_query(
        "DELETE FROM report WHERE report_id = {{reportId::uuid}}",
        {"reportId": report_id},
    )
    return True
