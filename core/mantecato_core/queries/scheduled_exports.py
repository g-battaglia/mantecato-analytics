"""
Scheduled export CRUD operations and cron logic.

Scheduled exports are stored in the `report` table with type = 'mantecato-scheduled-export'.
The `parameters` JSONB column holds the ScheduledExportConfig:
  {websiteId, dataSource, format, dateRange, schedule, weekDay?, monthDay?,
   enabled, lastRunAt?, nextRunAt?}
Converted from Prisma ORM to raw SQL.
"""

import json
import uuid
from datetime import datetime
from typing import Any

from mantecato_core.database import raw_query


SCHEDULED_EXPORT_TYPE = "mantecato-scheduled-export"


def _report_to_scheduled_export(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a report row to a scheduled export dict."""
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


def compute_next_run(config: dict[str, Any]) -> datetime:
    """Compute the next run datetime based on the schedule config."""
    now = datetime.utcnow()
    schedule = config.get("schedule", "daily")

    if schedule == "daily":
        next_run = now.replace(hour=6, minute=0, second=0, microsecond=0)
        # If today's 06:00 has passed, schedule for tomorrow
        if next_run <= now:
            from datetime import timedelta

            next_run += timedelta(days=1)
        return next_run

    elif schedule == "weekly":
        target_day = config.get("weekDay", 1)  # Default Monday
        current_day = now.weekday()  # Monday=0, Sunday=6
        # Convert JS day (0=Sun) to Python weekday (0=Mon)
        # JS: Sun=0, Mon=1, Tue=2, ... Sat=6
        # Python: Mon=0, Tue=1, ... Sun=6
        py_target = (target_day - 1) % 7 if target_day != 0 else 6
        days_ahead = (py_target - current_day) % 7
        if days_ahead == 0:
            days_ahead = 7  # Always at least a week away (or tomorrow if today)
            # Check if today's 06:00 hasn't passed yet
            next_run = now.replace(hour=6, minute=0, second=0, microsecond=0)
            if next_run > now:
                days_ahead = 0
        from datetime import timedelta

        next_run = (now + timedelta(days=days_ahead)).replace(
            hour=6, minute=0, second=0, microsecond=0
        )
        return next_run

    elif schedule == "monthly":
        target_day = min(config.get("monthDay", 1), 28)
        # Next month
        if now.month == 12:
            next_run = now.replace(
                year=now.year + 1,
                month=1,
                day=target_day,
                hour=6,
                minute=0,
                second=0,
                microsecond=0,
            )
        else:
            next_run = now.replace(
                month=now.month + 1,
                day=target_day,
                hour=6,
                minute=0,
                second=0,
                microsecond=0,
            )
        return next_run

    else:
        from datetime import timedelta

        return now + timedelta(hours=24)


async def list_scheduled_exports(user_id: str) -> list[dict[str, Any]]:
    """List all scheduled exports for a user."""
    rows = await raw_query(
        """SELECT report_id, name, description, user_id, website_id, parameters, created_at, updated_at
           FROM report
           WHERE type = {{type}}
             AND user_id = {{userId::uuid}}
           ORDER BY updated_at DESC""",
        {"type": SCHEDULED_EXPORT_TYPE, "userId": user_id},
    )
    return [_report_to_scheduled_export(r) for r in rows]


async def get_scheduled_export(report_id: str, user_id: str) -> dict[str, Any] | None:
    """Get a single scheduled export."""
    rows = await raw_query(
        """SELECT report_id, name, description, user_id, website_id, parameters, created_at, updated_at
           FROM report
           WHERE report_id = {{reportId::uuid}}
             AND type = {{type}}
             AND user_id = {{userId::uuid}}""",
        {"reportId": report_id, "type": SCHEDULED_EXPORT_TYPE, "userId": user_id},
    )
    return _report_to_scheduled_export(rows[0]) if rows else None


async def create_scheduled_export(
    user_id: str,
    name: str,
    description: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Create a new scheduled export. Computes initial nextRunAt."""
    config["nextRunAt"] = compute_next_run(config).isoformat()

    report_id = str(uuid.uuid4())
    website_id = config.get("websiteId", "")

    await raw_query(
        """INSERT INTO report (report_id, user_id, website_id, type, name, description, parameters)
           VALUES ({{id::uuid}}, {{userId::uuid}}, {{websiteId::uuid}}, {{type}}, {{name}}, {{description}}, {{params}}::jsonb)""",
        {
            "id": report_id,
            "userId": user_id,
            "websiteId": website_id,
            "type": SCHEDULED_EXPORT_TYPE,
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
    return _report_to_scheduled_export(row[0])


async def update_scheduled_export(
    report_id: str,
    user_id: str,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    """Update a scheduled export. Recalculates nextRunAt if schedule changed."""
    existing = await raw_query(
        """SELECT report_id, name, description, user_id, website_id, parameters, created_at, updated_at
           FROM report
           WHERE report_id = {{reportId::uuid}}
             AND type = {{type}}
             AND user_id = {{userId::uuid}}""",
        {"reportId": report_id, "type": SCHEDULED_EXPORT_TYPE, "userId": user_id},
    )
    if not existing:
        return None

    set_parts: list[str] = []
    params: dict[str, Any] = {
        "reportId": report_id,
        "type": SCHEDULED_EXPORT_TYPE,
        "userId": user_id,
    }

    if "name" in updates and updates["name"] is not None:
        set_parts.append("name = {{name}}")
        params["name"] = updates["name"]

    if "description" in updates and updates["description"] is not None:
        set_parts.append("description = {{description}}")
        params["description"] = updates["description"]

    if "config" in updates and updates["config"] is not None:
        existing_config = existing[0].get("parameters", {})
        if isinstance(existing_config, str):
            existing_config = json.loads(existing_config)

        merged = {**existing_config, **updates["config"]}

        # Recalculate next run if schedule or enabled flag changed
        if "schedule" in updates["config"] or "enabled" in updates["config"]:
            merged["nextRunAt"] = (
                compute_next_run(merged).isoformat() if merged.get("enabled") else None
            )

        set_parts.append("parameters = {{params}}::jsonb")
        params["params"] = json.dumps(merged)

    if not set_parts:
        return _report_to_scheduled_export(existing[0])

    set_clause = ", ".join(set_parts)
    rows = await raw_query(
        f"UPDATE report SET {set_clause}, updated_at = NOW() WHERE report_id = {{reportId::uuid}} RETURNING report_id, name, description, user_id, website_id, parameters, created_at, updated_at",
        params,
    )
    return _report_to_scheduled_export(rows[0])


async def delete_scheduled_export(report_id: str, user_id: str) -> bool:
    """Delete a scheduled export. Returns True if deleted, False if not found."""
    existing = await raw_query(
        """SELECT report_id FROM report
           WHERE report_id = {{reportId::uuid}}
             AND type = {{type}}
             AND user_id = {{userId::uuid}}""",
        {"reportId": report_id, "type": SCHEDULED_EXPORT_TYPE, "userId": user_id},
    )
    if not existing:
        return False

    await raw_query(
        "DELETE FROM report WHERE report_id = {{reportId::uuid}}",
        {"reportId": report_id},
    )
    return True


async def get_due_exports() -> list[dict[str, Any]]:
    """Get all due exports (nextRunAt <= now, enabled=true). Used by the cron endpoint."""
    rows = await raw_query(
        """SELECT report_id, name, description, user_id, website_id, parameters, created_at, updated_at
           FROM report
           WHERE type = {{type}}""",
        {"type": SCHEDULED_EXPORT_TYPE},
    )

    now = datetime.utcnow()
    exports = [_report_to_scheduled_export(r) for r in rows]

    return [
        e
        for e in exports
        if e["config"].get("enabled")
        and e["config"].get("nextRunAt")
        and datetime.fromisoformat(e["config"]["nextRunAt"]) <= now
    ]


async def mark_export_completed(report_id: str) -> None:
    """Mark an export as completed and schedule the next run."""
    rows = await raw_query(
        """SELECT report_id, parameters FROM report WHERE report_id = {{reportId::uuid}}""",
        {"reportId": report_id},
    )
    if not rows:
        return

    config = rows[0].get("parameters", {})
    if isinstance(config, str):
        config = json.loads(config)

    config["lastRunAt"] = datetime.utcnow().isoformat()
    config["nextRunAt"] = compute_next_run(config).isoformat()

    await raw_query(
        """UPDATE report SET parameters = {{params}}::jsonb, updated_at = NOW()
           WHERE report_id = {{reportId::uuid}}""",
        {"params": json.dumps(config), "reportId": report_id},
    )
