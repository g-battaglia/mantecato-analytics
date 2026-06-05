"""Base class and declarative utilities for analytics page views.

Extracted from ``views.py`` to keep the view module focused on concrete
page declarations.  Contains three building blocks:

- :class:`ChartMapping` — **Strategy pattern**: a frozen descriptor that
  pairs a service data key with its chart builder, so the view doesn't
  need to call each builder manually.
- :func:`build_chart_context` — applies a list of :class:`ChartMapping`
  to a service result dict, producing the merged template context.
- :class:`AnalyticsBase` — **Template Method**: abstract base for every
  analytics page view.  It layers five composable mixins (each adding one
  concern: auth, website, date range, filters, base context) and encodes
  the "no data → empty state" convention.  Concrete views configure it
  via class attributes (``_service``, ``_charts``) or method overrides.

Composition over Inheritance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The design favors **composition via mixins** over a deep class hierarchy:

- ``LoginRequiredMixin`` — authentication gate (Django built-in)
- ``WebsiteContextMixin`` — resolves ``?website=`` to an accessible site
- ``DateRangeMixin`` — resolves ``?range=`` or ``?start=/end=``
- ``FiltersMixin`` — parses ``?filter=column:op:value``
- ``BaseContextMixin`` — injects common template variables

Each mixin is independent and adds exactly one concern.  The view itself
adds only its ``_service`` strategy and ``_charts`` mapping — there is no
second level of analytics-specific inheritance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.common.mixins import (
    BaseContextMixin,
    DateRangeMixin,
    FiltersMixin,
    WebsiteContextMixin,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


# ============================================================================
# Chart-mapping utility — Strategy pattern for service → Chart.js transform
# ============================================================================


@dataclass(frozen=True, slots=True)
class ChartMapping:
    """Declarative descriptor: service data key → chart builder → context key.

    Instead of writing the repetitive pattern::

        data = get_pages_data(...)
        return {
            "pages_chart_data": build_pages_bar_chart_data(data["pages"]),
            **data,
        }

    you declare a mapping and let :func:`build_chart_context` apply it::

        _charts = [ChartMapping("pages_chart_data", build_pages_bar, "pages")]

    This is the **Strategy pattern**: the builder function is a pluggable
    strategy that transforms one data key into a Chart.js payload.

    Attributes:
        context_key: Template variable name for the Chart.js payload.
        builder: Chart builder function (from ``chart_data.py``).
        data_key: Key to extract from the service result dict.
        default: Fallback when ``data_key`` is absent (default: ``[]``,
            which produces an empty chart).
    """

    context_key: str
    builder: Callable
    data_key: str
    default: Any = field(default_factory=list)


def build_chart_context(data: dict, charts: Sequence[ChartMapping]) -> dict:
    """Apply chart mappings to a service result, producing template context.

    Creates a **new** dict containing all original service data plus the
    generated Chart.js payloads.  The original dict is not mutated.

    This function centralises the "data → chart payload" transform that
    was previously scattered across every view's ``get_service_data``.

    Args:
        data: Raw result dict from a service function.
        charts: Sequence of :class:`ChartMapping` descriptors.

    Returns:
        Merged dict with original data + chart payloads, ready for the
        Django template.

    Example::

        data = get_pages_data(website_id, date_range, filters)
        ctx = build_chart_context(data, [
            ChartMapping("pages_chart", build_pages_bar, "pages"),
        ])
        # ctx contains all of `data` plus "pages_chart" key
    """
    ctx = dict(data)
    for c in charts:
        ctx[c.context_key] = c.builder(data.get(c.data_key, c.default))
    return ctx


# ============================================================================
# Abstract base — Template Method for all analytics page views
# ============================================================================


class AnalyticsBase(
    LoginRequiredMixin,
    WebsiteContextMixin,
    DateRangeMixin,
    FiltersMixin,
    BaseContextMixin,
    TemplateView,
):
    """Abstract base for every full-page analytics view.

    Provides three levels of configuration, from most declarative to
    most flexible:

    **Level 1 — Pure declaration** (e.g. ``SectionsView``)::

        class SectionsView(AnalyticsBase):
            template_name = "analytics/sections.html"
            _charts = [ChartMapping(...)]

            def _call_service(self):
                return get_sections_data(self.website_id, ...)

    **Level 2 — Custom chart assembly** (e.g. ``SourcesView``):
        Override ``get_service_data()`` and use ``build_chart_context``
        for the standard mappings, plus manual calls for non-standard
        builders.

    **Level 3 — Full override** (e.g. ``OverviewView``, ``JourneysView``):
        Override ``get_service_data()`` entirely for pages that call
        multiple services or build charts with non-standard signatures.

    Attributes:
        template_name: Path to the page template.
        no_data_template: Fallback template when no website/date range.
        _charts: Sequence of :class:`ChartMapping` descriptors applied
            by the default ``get_service_data()`` implementation.
    """

    no_data_template = "analytics/overview.html"
    _charts: ClassVar[Sequence[ChartMapping]] = ()

    # -- Template resolution --------------------------------------------------

    @property
    def has_data(self) -> bool:
        """True when both a website and a date range are resolved."""
        return bool(self.website_id and self.date_range)

    def get_template_names(self) -> list[str]:
        """Swap in the empty-state overview when context is incomplete."""
        if not self.has_data:
            return [self.no_data_template]
        return [self.template_name]

    # -- Context assembly (Template Method) -----------------------------------

    def get_context_data(self, **kwargs: object) -> dict:
        """Merge base context with service data, or set the no-data flag.

        This is the Template Method entry point.  Subclasses customize
        by overriding ``get_service_data()`` or ``_call_service()``.
        """
        ctx = super().get_context_data(**kwargs)
        if not self.has_data:
            ctx["no_data"] = True
            return ctx
        return {**ctx, **self.get_service_data()}

    def get_service_data(self) -> dict:
        """Fetch data and build the template context.

        The default implementation calls ``_call_service()`` and applies
        ``_charts``.  Override for pages that need fully custom assembly
        (multiple service calls, non-standard chart builders).
        """
        data = self._call_service()
        if self._charts:
            return build_chart_context(data, self._charts)
        return data

    def _call_service(self) -> dict:
        """Invoke the page's service function.

        Override this to pass extra GET parameters (page number, country
        drill-down, granularity, etc.) while keeping ``_charts`` active.
        The base implementation raises ``NotImplementedError`` because
        every concrete view must define its own service call.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must override _call_service() or get_service_data()"
        )
