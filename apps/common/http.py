"""Shared HTTP helpers used across the web and API layers.

Query-string parsing (:func:`safe_int`) is the only utility that
survived the Phase 1 refactor — request-body parsing moved to
:class:`~apps.common.json_views.JSONFormView`, and API-key auth
moved to :class:`~apps.common.mixins.ApiAuthMixin`.
"""

from __future__ import annotations


def safe_int(value: str | None, default: int = 1) -> int:
    """Parse *value* as an int ≥ 1, falling back to *default* on bad input.

    Used by paginated endpoints (``?page=`` / ``?limit=`` / ``?window=``) to
    avoid raising 500 errors on garbage query strings.
    """
    try:
        return max(1, int(value or default))
    except (TypeError, ValueError):
        return default
