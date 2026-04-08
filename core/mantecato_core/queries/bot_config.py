"""
Bot detection config CRUD operations.

Config is stored in the `report` table with type = 'mantecato-bot-config'.
One record per website. The `parameters` JSONB column holds the full config.
"""

import json
import uuid
from datetime import datetime
from typing import Any

from mantecato_core.database import raw_query


BOT_CONFIG_TYPE = "mantecato-bot-config"

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "knownBots": True,
    "emptyUa": True,
    "clusterDetection": True,
    "clusterBounceThreshold": 90,
    "clusterMinSize": 100,
    "zeroEngagement": False,
    "minDuration": 0,
    "missingScreen": False,
    "missingLanguage": False,
    "highVelocityThreshold": 60,
    "excludedCountries": [],
}


def _merge_defaults(params: dict[str, Any]) -> dict[str, Any]:
    """Merge stored params with defaults for any missing keys."""
    merged = {**DEFAULT_CONFIG}
    for key, value in params.items():
        if key in merged:
            merged[key] = value
    return merged


def _report_to_config(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a report row to a bot config dict."""
    params = row.get("parameters", {})
    if isinstance(params, str):
        params = json.loads(params)

    config = _merge_defaults(params)

    created_at = row.get("created_at")
    updated_at = row.get("updated_at")

    return {
        "id": row["report_id"],
        "websiteId": row.get("website_id", ""),
        "config": config,
        "createdAt": created_at.isoformat()
        if isinstance(created_at, datetime)
        else None,
        "updatedAt": updated_at.isoformat()
        if isinstance(updated_at, datetime)
        else None,
    }


async def get_bot_config(website_id: str) -> dict[str, Any] | None:
    """Get bot config for a website. Returns None if no config saved."""
    rows = await raw_query(
        """SELECT report_id, user_id, website_id, parameters, created_at, updated_at
           FROM report
           WHERE type = {{type}}
             AND website_id = {{websiteId::uuid}}
           LIMIT 1""",
        {"type": BOT_CONFIG_TYPE, "websiteId": website_id},
    )
    if not rows:
        return None
    return _report_to_config(rows[0])


async def get_bot_config_or_defaults(website_id: str) -> dict[str, Any]:
    """Get bot config for a website, returning defaults if none saved."""
    existing = await get_bot_config(website_id)
    if existing:
        return existing
    return {
        "id": None,
        "websiteId": website_id,
        "config": {**DEFAULT_CONFIG},
        "createdAt": None,
        "updatedAt": None,
    }


async def upsert_bot_config(
    user_id: str,
    website_id: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Create or update bot config for a website."""
    merged = _merge_defaults(config)
    params_json = json.dumps(merged)

    existing = await raw_query(
        """SELECT report_id FROM report
           WHERE type = {{type}}
             AND website_id = {{websiteId::uuid}}
           LIMIT 1""",
        {"type": BOT_CONFIG_TYPE, "websiteId": website_id},
    )

    if existing:
        report_id = existing[0]["report_id"]
        await raw_query(
            """UPDATE report
               SET parameters = {{params}}::jsonb,
                   updated_at = NOW()
               WHERE report_id = {{id::uuid}}""",
            {"id": str(report_id), "params": params_json},
        )
    else:
        report_id = str(uuid.uuid4())
        await raw_query(
            """INSERT INTO report (report_id, user_id, website_id, type, name, description, parameters)
               VALUES ({{id::uuid}}, {{userId::uuid}}, {{websiteId::uuid}}, {{type}}, {{name}}, {{description}}, {{params}}::jsonb)""",
            {
                "id": report_id,
                "userId": user_id,
                "websiteId": website_id,
                "type": BOT_CONFIG_TYPE,
                "name": "Bot Detection Config",
                "description": "",
                "params": params_json,
            },
        )

    row = await raw_query(
        """SELECT report_id, user_id, website_id, parameters, created_at, updated_at
           FROM report WHERE report_id = {{id::uuid}}""",
        {"id": str(report_id)},
    )
    return _report_to_config(row[0])
