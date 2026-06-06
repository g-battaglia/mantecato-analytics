"""JSON serialization helpers for API responses.

Handles types that Django's JsonResponse cannot natively encode:
datetime, date, time, Decimal, UUID, bytes.
"""

from __future__ import annotations

import decimal
import uuid
from datetime import date, datetime, time
from typing import Any


def sanitize_for_json(obj: Any) -> Any:
    """Recursively convert non-JSON-serializable types to safe primitives."""
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(item) for item in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, time):
        return obj.isoformat()
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    return obj
