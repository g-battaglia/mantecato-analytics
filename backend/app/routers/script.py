"""
Script route — GET /api/script serves the tracker JS file.
"""

from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter(prefix="/api", tags=["script"])


@router.get("/script")
async def get_script():
    """Serve the Mantecato tracker script as a JS file."""
    script_path = os.path.join(
        os.getcwd(),
        "packages",
        "tracker",
        "dist",
        "script.js",
    )

    try:
        with open(script_path, "r") as f:
            script = f.read()

        return Response(
            content=script,
            media_type="application/javascript; charset=utf-8",
            headers={
                "Cache-Control": "public, max-age=86400, s-maxage=86400",
                "X-Content-Type-Options": "nosniff",
            },
        )
    except FileNotFoundError:
        return {
            "error": "Tracker script not found. Run: npm run build -w @mantecato/tracker"
        }
