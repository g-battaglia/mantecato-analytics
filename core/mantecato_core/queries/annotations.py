"""
Annotation CRUD operations.

Annotations are stored in the `report` table with type = 'mantecato-annotation'.
The `parameters` JSONB column holds: {date: ISO string, color: string}.
Converted from Prisma ORM to raw SQL.
"""

import json
import uuid
from datetime import datetime
from typing import Any

from mantecato_core.database import raw_query


ANNOTATION_TYPE = "mantecato-annotation"


def _report_to_annotation(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a report row to an annotation dict."""
    params = row.get("parameters", {})
    if isinstance(params, str):
        params = json.loads(params)

    created_at = row.get("created_at")
    updated_at = row.get("updated_at")

    return {
        "id": row["report_id"],
        "userId": row.get("user_id", ""),
        "websiteId": row.get("website_id", ""),
        "title": row.get("name", ""),
        "description": row.get("description", ""),
        "date": params.get("date")
        or (
            created_at.isoformat()
            if isinstance(created_at, datetime)
            else datetime.utcnow().isoformat()
        ),
        "color": params.get("color", "blue"),
        "createdAt": created_at.isoformat()
        if isinstance(created_at, datetime)
        else datetime.utcnow().isoformat(),
        "updatedAt": updated_at.isoformat()
        if isinstance(updated_at, datetime)
        else datetime.utcnow().isoformat(),
    }


async def list_annotations(
    user_id: str,
    website_id: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[dict[str, Any]]:
    """List annotations for a website, optionally filtered by date range."""
    rows = await raw_query(
        """SELECT report_id, user_id, website_id, name, description, parameters, created_at, updated_at
           FROM report
           WHERE type = {{type}}
             AND user_id = {{userId::uuid}}
             AND website_id = {{websiteId::uuid}}
           ORDER BY created_at DESC""",
        {"type": ANNOTATION_TYPE, "userId": user_id, "websiteId": website_id},
    )

    annotations = [_report_to_annotation(r) for r in rows]

    # Filter by date range if provided (in-memory, matching TS behavior)
    if start_date and end_date:
        start_iso = start_date.isoformat()
        end_iso = end_date.isoformat()
        annotations = [a for a in annotations if start_iso <= a["date"] <= end_iso]

    return annotations


async def create_annotation(
    user_id: str,
    website_id: str,
    title: str,
    description: str,
    date: str,
    color: str = "blue",
) -> dict[str, Any]:
    """Create a new annotation."""
    report_id = str(uuid.uuid4())
    config = json.dumps({"date": date, "color": color})

    await raw_query(
        """INSERT INTO report (report_id, user_id, website_id, type, name, description, parameters)
           VALUES ({{id::uuid}}, {{userId::uuid}}, {{websiteId::uuid}}, {{type}}, {{name}}, {{description}}, {{params}}::jsonb)""",
        {
            "id": report_id,
            "userId": user_id,
            "websiteId": website_id,
            "type": ANNOTATION_TYPE,
            "name": title,
            "description": description or "",
            "params": config,
        },
    )

    # Fetch back the created row to get server-generated timestamps
    row = await raw_query(
        """SELECT report_id, user_id, website_id, name, description, parameters, created_at, updated_at
           FROM report WHERE report_id = {{id::uuid}}""",
        {"id": report_id},
    )
    return _report_to_annotation(row[0])


async def delete_annotation(report_id: str, user_id: str) -> bool:
    """Delete an annotation. Returns True if deleted, False if not found."""
    existing = await raw_query(
        """SELECT report_id FROM report
           WHERE report_id = {{reportId::uuid}}
             AND type = {{type}}
             AND user_id = {{userId::uuid}}""",
        {"reportId": report_id, "type": ANNOTATION_TYPE, "userId": user_id},
    )
    if not existing:
        return False

    await raw_query(
        "DELETE FROM report WHERE report_id = {{reportId::uuid}}",
        {"reportId": report_id},
    )
    return True
