"""Render a shields-style flat SVG badge — dependency-free, first-party.

Used by the native ``/api/badge`` endpoint so Mantecato can serve its own
README view-counter badge instead of a third-party service. Pure string
building: no network, no external library. Inputs are sanitised (XML-escaped,
length-clamped; the colour is validated against a hex/name allow-list) so the
public endpoint cannot be used to inject markup into the SVG.
"""

from __future__ import annotations

import html
import re

# Approx. average glyph width at the badge font size, plus per-segment padding.
_CHAR_W = 7.0
_PAD = 10
_HEIGHT = 20

_DEFAULT_COLOR = "#4c1"
_HEX_RE = re.compile(r"^#?[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?$")
_NAMED_COLORS = {
    "green": "#4c1",
    "brightgreen": "#4c1",
    "blue": "#007ec6",
    "grey": "#555",
    "gray": "#555",
    "lightgrey": "#9f9f9f",
    "red": "#e05d44",
    "orange": "#fe7d37",
    "yellow": "#dfb317",
    "purple": "#9b59b6",
}

_MAX_LABEL = 32
_MAX_VALUE = 16


def safe_color(color: str | None) -> str:
    """Return a safe CSS colour: an allow-listed name or ``#hex``, else the default."""
    if not color:
        return _DEFAULT_COLOR
    c = color.strip().lower()
    if c in _NAMED_COLORS:
        return _NAMED_COLORS[c]
    if _HEX_RE.match(c):
        return c if c.startswith("#") else f"#{c}"
    return _DEFAULT_COLOR


def _seg_width(text: str) -> int:
    return int(len(text) * _CHAR_W) + _PAD


def render_badge(label: str, value: str, color: str | None = None) -> str:
    """Return a flat two-segment SVG badge: ``[ label | value ]``.

    Args:
        label: Left (grey) segment text, e.g. ``"views"``.
        value: Right (coloured) segment text, e.g. ``"3.48K"``.
        color: Right-segment colour (name or ``#hex``); falls back to green.
    """
    label = (label or "")[:_MAX_LABEL]
    value = (value or "")[:_MAX_VALUE]
    fill = safe_color(color)

    lw = _seg_width(label)
    vw = _seg_width(value)
    total = lw + vw

    le = html.escape(label, quote=True)
    ve = html.escape(value, quote=True)

    # Text is drawn at 10x then scaled 0.1 (the shields-flat trick) for crisp
    # sub-pixel positioning; centres and textLengths are in that 10x space.
    lx = lw * 5
    vx = lw * 10 + vw * 5
    ltl = max(0, lw - _PAD) * 10
    vtl = max(0, vw - _PAD) * 10
    aria = f"{le}: {ve}"

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="{_HEIGHT}" '
        f'role="img" aria-label="{aria}">'
        f"<title>{aria}</title>"
        '<linearGradient id="s" x2="0" y2="100%">'
        '<stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
        '<stop offset="1" stop-opacity=".1"/></linearGradient>'
        f'<clipPath id="r"><rect width="{total}" height="{_HEIGHT}" rx="3" fill="#fff"/></clipPath>'
        '<g clip-path="url(#r)">'
        f'<rect width="{lw}" height="{_HEIGHT}" fill="#555"/>'
        f'<rect x="{lw}" width="{vw}" height="{_HEIGHT}" fill="{fill}"/>'
        f'<rect width="{total}" height="{_HEIGHT}" fill="url(#s)"/></g>'
        '<g fill="#fff" text-anchor="middle" '
        'font-family="Verdana,Geneva,DejaVu Sans,sans-serif" '
        'font-size="110" text-rendering="geometricPrecision">'
        f'<text x="{lx}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" '
        f'textLength="{ltl}">{le}</text>'
        f'<text x="{lx}" y="140" transform="scale(.1)" textLength="{ltl}">{le}</text>'
        f'<text x="{vx}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" '
        f'textLength="{vtl}">{ve}</text>'
        f'<text x="{vx}" y="140" transform="scale(.1)" textLength="{vtl}">{ve}</text>'
        "</g></svg>"
    )
