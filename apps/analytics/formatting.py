"""Display-formatting helpers extracted from :mod:`apps.analytics.services`.

Keeping these out of ``services.py`` separates "shape the data" (services)
from "humanise the numbers for the UI" (here). The functions are pure,
have no Django imports, and are unit-test-friendly.

Cross-refs:
    - :mod:`apps.analytics.services` — primary consumer.
    - :mod:`core.mantecato_core.helpers` — the legacy CLI/MCP variants
      (``format_duration``, ``pct_change``) that live there are kept
      separate to avoid breaking the CLI surface.
"""

from __future__ import annotations


def format_compact(value: int | float) -> str:
    """Render a number with thousands/millions suffixes for compact display.

    Converts large numbers into human-readable abbreviated strings using K
    (thousands) and M (millions) suffixes.  Used by the analytics stat-card
    templates to fit large values into small UI elements.

    The formatting rules are:

    - **Floats with fractional parts** always show two decimal places at every
      magnitude (e.g. ``1234.5`` -> ``"1.23K"``).
    - **Integers >= 1M** show two decimals if the result is not whole
      (``1_510_000`` -> ``"1.51M"``, ``2_000_000`` -> ``"2M"``).
    - **Integers >= 1K** follow the same whole-number logic
      (``1_510`` -> ``"1.51K"``, ``2_000`` -> ``"2K"``).
    - **Integers < 1K** are returned as plain strings (``42`` -> ``"42"``).

    Args:
        value: The numeric value to format.  Accepts both int and float.

    Returns:
        A compact string representation.

    Examples::

        >>> format_compact(42)
        '42'
        >>> format_compact(1234)
        '1.23K'
        >>> format_compact(2000)
        '2K'
        >>> format_compact(1_510_000)
        '1.51M'
        >>> format_compact(2_000_000)
        '2M'
        >>> format_compact(99.7)
        '99.70'
    """
    if isinstance(value, float) and not value.is_integer():
        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:.2f}M"
        if abs(value) >= 1_000:
            return f"{value / 1_000:.2f}K"
        return f"{value:.2f}"
    value = int(value)
    if abs(value) >= 1_000_000:
        v = value / 1_000_000
        return f"{v:.2f}M" if v != int(v) else f"{int(v)}M"
    if abs(value) >= 1_000:
        v = value / 1_000
        return f"{v:.2f}K" if v != int(v) else f"{int(v)}K"
    return str(value)


def percentage_change(current: float, previous: float) -> dict | None:
    """Compute the percentage change between two period values for KPI badges.

    Used by ``_stats_with_change`` to generate the colored trend badges shown
    on analytics stat cards.  The trend direction determines the badge color
    in the template (green for "up", red for "down", gray for "flat").

    Args:
        current: The metric value for the current (most recent) period.
        previous: The metric value for the comparison (earlier) period.

    Returns:
        A dict ``{"value": "<pct>%", "trend": "up"|"down"|"flat"}`` describing
        the change, or ``None`` when both values are zero (no meaningful change).

        The ``value`` string always shows the absolute percentage with one
        decimal place (e.g. ``"12.3%"``).  The sign is conveyed by ``trend``.

    Special cases:
        - ``previous == 0`` and ``current > 0``: returns
          ``{"value": "100%", "trend": "up"}`` -- interpreted by the UI as
          "first non-zero data point".
        - ``previous == 0`` and ``current == 0``: returns ``None`` -- no badge
          is rendered.

    Examples::

        >>> percentage_change(150, 100)
        {'value': '50.0%', 'trend': 'up'}
        >>> percentage_change(80, 100)
        {'value': '20.0%', 'trend': 'down'}
        >>> percentage_change(100, 100)
        {'value': '0.0%', 'trend': 'flat'}
        >>> percentage_change(50, 0)
        {'value': '100%', 'trend': 'up'}
        >>> percentage_change(0, 0) is None
        True
    """
    if previous == 0:
        if current > 0:
            return {"value": "100%", "trend": "up"}
        return None
    change = ((current - previous) / previous) * 100
    trend = "up" if change > 0 else "down" if change < 0 else "flat"
    return {"value": f"{abs(change):.1f}%", "trend": trend}


def format_duration(total_seconds: int) -> str:
    """Render a number of seconds as a compact human-readable duration string.

    Converts raw seconds into the most appropriate time unit representation.
    Used by the analytics stat cards and session tables to display average
    session duration and time-on-page values.

    The output format depends on the magnitude:

    - **< 60 seconds**: ``"{n}s"`` (e.g. ``"45s"``).
    - **1--59 minutes**: ``"{m}m {s}s"`` (e.g. ``"3m 12s"``).
    - **>= 60 minutes**: ``"{h}h {m}m"`` (e.g. ``"1h 30m"``).

    Args:
        total_seconds: Non-negative integer number of seconds to format.

    Returns:
        A compact duration string.

    Examples::

        >>> format_duration(0)
        '0s'
        >>> format_duration(45)
        '45s'
        >>> format_duration(192)
        '3m 12s'
        >>> format_duration(5400)
        '1h 30m'
    """
    if total_seconds < 60:
        return f"{total_seconds}s"
    minutes, seconds = divmod(total_seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"
