"""Custom template filters/tags for number formatting and view-state links.

Provides the ``intcomma`` filter used across analytics templates to render
large numbers with thousands separators (e.g. ``1234567`` becomes
``1,234,567``), and the ``view_query`` tag that preserves the current
analytics view state (website, date range, filters, bot filter) across
navigation links.

Usage in templates::

    {% load fmt %}
    {{ pageviews|intcomma }}
    <a href="{% url 'analytics_sources' %}?{% view_query %}">Sources</a>
"""

from urllib.parse import urlencode

from django import template

register = template.Library()

# Query-string keys that make up the "view state" of an analytics page.
# These must survive navigation between pages so that switching section
# does not silently drop the active date range, filters, or bot filter.
_VIEW_STATE_KEYS = ("website", "range", "start", "end", "filter", "f", "bot_filter", "offset")


@register.simple_tag(takes_context=True)
def view_query(context):
    """Return the current view-state as a URL-encoded query string.

    Reads the preserved keys (:data:`_VIEW_STATE_KEYS`) from the current
    request's query string, keeping multi-valued keys (``filter``/``f``)
    intact, and falls back to the resolved ``selected_website`` from the
    template context when ``website`` is absent from the URL (e.g. on the
    default overview, which has no explicit ``?website=``).

    Empty values are skipped so the resulting string stays clean. Intended
    to be used right after ``?`` in nav and "View all" links::

        <a href="{% url 'analytics_devices' %}?{% view_query %}">Devices</a>
    """
    request = context.get("request")
    pairs: list[tuple[str, str]] = []
    has_website = False
    if request is not None:
        for key in _VIEW_STATE_KEYS:
            for value in request.GET.getlist(key):
                if value != "":
                    pairs.append((key, value))
                    if key == "website":
                        has_website = True
    # Ensure the selected website always rides along, even when it was
    # resolved implicitly (no ?website= in the URL).
    if not has_website:
        selected = context.get("selected_website")
        if selected:
            pairs.insert(0, ("website", str(selected)))
    return urlencode(pairs)


@register.filter
def intcomma(value):
    """Format an integer with comma-separated thousands.

    Silently returns the original value when it cannot be coerced to an
    integer -- this avoids template rendering errors on ``None`` or
    non-numeric strings.

    Args:
        value: A number or string coercible to ``int``.

    Returns:
        A comma-formatted string (e.g. ``"1,234,567"``), or the original
        *value* unchanged when conversion fails.
    """
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return value
