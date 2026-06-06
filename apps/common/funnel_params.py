"""Funnel-step query-parameter parser.

The analytics web view and the JSON API endpoint accept funnel definitions
using the numbered-pair convention introduced by the upstream Umami tracker:
``?step_type.0=url&step_value.0=/&step_type.1=event&step_value.1=signup``.

The original code duplicated the parsing helper across
:mod:`apps.analytics.views` and :mod:`apps.api.views`. Both call sites now
delegate to :func:`parse_funnel_steps` here.

Example:
    >>> from django.http import QueryDict
    >>> parse_funnel_steps(QueryDict("step_type.0=url&step_value.0=/"))
    [{'type': 'url', 'value': '/'}]
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http.request import QueryDict


_ALLOWED_STEP_TYPES = ("url", "event")


def parse_funnel_steps(params: QueryDict) -> list[dict[str, str]]:
    """Extract funnel steps from ``step_type.N`` / ``step_value.N`` pairs.

    Iterates ``N = 0, 1, 2, ...`` until a missing pair or an invalid step type
    is found. The result preserves the user-supplied order.

    Args:
        params: A Django :class:`~django.http.request.QueryDict` (usually
            ``request.GET``).

    Returns:
        Ordered list of ``{"type": str, "value": str}`` dicts. Empty if the
        first pair is missing or has an invalid ``type`` (anything other than
        ``"url"`` or ``"event"``).

    Example:
        >>> from django.http import QueryDict
        >>> qd = QueryDict(
        ...     "step_type.0=url&step_value.0=/&step_type.1=event&step_value.1=signup"
        ... )
        >>> parse_funnel_steps(qd)
        [{'type': 'url', 'value': '/'}, {'type': 'event', 'value': 'signup'}]

    Cross-refs:
        - :func:`core.mantecato_core.queries.funnels.get_funnel`
        - :class:`apps.api.views.AnalyticsFunnelsView`
        - :class:`apps.analytics.views.FunnelsView`
    """
    steps: list[dict[str, str]] = []
    index = 0
    while True:
        step_type = params.get(f"step_type.{index}")
        step_value = params.get(f"step_value.{index}")
        if not step_type or not step_value:
            break
        if step_type not in _ALLOWED_STEP_TYPES:
            break
        steps.append({"type": step_type, "value": step_value})
        index += 1
    return steps
