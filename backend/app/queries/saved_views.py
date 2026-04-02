"""
Saved view CRUD operations.

Saved views are stored in the `report` table with type = 'mantecato-saved-view'.
The `parameters` JSONB column holds the SavedViewConfig object:
  {preset, customStart?, customEnd?, granularity, filters[], page?}
Converted from Prisma ORM to raw SQL.
"""

import json
import uuid
from datetime import datetime
from typing import Any

from ..database import raw_query


SAVED_VIEW_TYPE = "mantecato-saved-view"


def _report_to_saved_view(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a report row to a saved view dict."""
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


async def list_saved_views(user_id: str, website_id: str) -> list[dict[str, Any]]:
    """List all saved views for a user+site."""
    rows = await raw_query(
        """SELECT report_id, name, description, user_id, website_id, parameters, created_at, updated_at
           FROM report
           WHERE type = {{type}}
             AND user_id = {{userId::uuid}}
             AND website_id = {{websiteId::uuid}}
           ORDER BY updated_at DESC""",
        {"type": SAVED_VIEW_TYPE, "userId": user_id, "websiteId": website_id},
    )
    return [_report_to_saved_view(r) for r in rows]


async def get_saved_view(report_id: str, user_id: str) -> dict[str, Any] | None:
    """Get a single saved view by ID."""
    rows = await raw_query(
        """SELECT report_id, name, description, user_id, website_id, parameters, created_at, updated_at
           FROM report
           WHERE report_id = {{reportId::uuid}}
             AND type = {{type}}
             AND user_id = {{userId::uuid}}""",
        {"reportId": report_id, "type": SAVED_VIEW_TYPE, "userId": user_id},
    )
    return _report_to_saved_view(rows[0]) if rows else None


async def create_saved_view(
    user_id: str,
    website_id: str,
    name: str,
    description: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Create a new saved view."""
    report_id = str(uuid.uuid4())

    await raw_query(
        """INSERT INTO report (report_id, user_id, website_id, type, name, description, parameters)
           VALUES ({{id::uuid}}, {{userId::uuid}}, {{websiteId::uuid}}, {{type}}, {{name}}, {{description}}, {{params}}::jsonb)""",
        {
            "id": report_id,
            "userId": user_id,
            "websiteId": website_id,
            "type": SAVED_VIEW_TYPE,
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
    return _report_to_saved_view(row[0])


async def update_saved_view(
    report_id: str,
    user_id: str,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    """Update a saved view. Returns the updated view or None if not found."""
    existing = await raw_query(
        """SELECT report_id, name, description, user_id, website_id, parameters, created_at, updated_at
           FROM report
           WHERE report_id = {{reportId::uuid}}
             AND type = {{type}}
             AND user_id = {{userId::uuid}}""",
        {"reportId": report_id, "type": SAVED_VIEW_TYPE, "userId": user_id},
    )
    if not existing:
        return None

    # Build SET clause dynamically
    set_parts: list[str] = []
    params: dict[str, Any] = {
        "reportId": report_id,
        "type": SAVED_VIEW_TYPE,
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
        return _report_to_saved_view(existing[0])

    set_clause = ", ".join(set_parts)
    rows = await raw_query(
        f"UPDATE report SET {set_clause}, updated_at = NOW() WHERE report_id = {{reportId::uuid}} RETURNING report_id, name, description, user_id, website_id, parameters, created_at, updated_at",
        params,
    )
    return _report_to_saved_view(rows[0])


async def delete_saved_view(report_id: str, user_id: str) -> bool:
    """Delete a saved view. Returns True if deleted, False if not found."""
    existing = await raw_query(
        """SELECT report_id FROM report
           WHERE report_id = {{reportId::uuid}}
             AND type = {{type}}
             AND user_id = {{userId::uuid}}""",
        {"reportId": report_id, "type": SAVED_VIEW_TYPE, "userId": user_id},
    )
    if not existing:
        return False

    await raw_query(
        "DELETE FROM report WHERE report_id = {{reportId::uuid}}",
        {"reportId": report_id},
    )
    return True
