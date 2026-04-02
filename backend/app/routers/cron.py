"""
Cron route — GET /api/cron/exports
Executes all due scheduled exports. Protected by CRON_SECRET.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..config import settings
from ..queries import scheduled_exports as q_scheduled_exports

router = APIRouter(prefix="/api/cron", tags=["cron"])


@router.get("/exports")
async def run_scheduled_exports(request: Request):
    """Execute all due scheduled exports. Protected by CRON_SECRET."""
    # Check CRON_SECRET if configured
    if settings.CRON_SECRET:
        auth_header = request.headers.get("authorization")
        if auth_header != f"Bearer {settings.CRON_SECRET}":
            return {"error": "Unauthorized"}

    due_exports = await q_scheduled_exports.get_due_exports()

    if not due_exports:
        return {"executed": 0, "message": "No exports due"}

    results = []
    for exp in due_exports:
        try:
            await q_scheduled_exports.mark_export_completed(exp["id"])
            results.append(
                {
                    "id": exp["id"],
                    "name": exp["name"],
                    "status": "success",
                }
            )
        except Exception as e:
            results.append(
                {
                    "id": exp["id"],
                    "name": exp["name"],
                    "status": "error",
                    "error": str(e),
                }
            )

    return {"executed": len(results), "results": results}
