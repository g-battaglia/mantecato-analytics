"""Additive API v1 views for remote CLI and MCP clients."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from django.db import DatabaseError, OperationalError
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

if TYPE_CHECKING:
    from django.http import HttpRequest, JsonResponse

from apps.api.v1.catalog import capabilities
from apps.api.v1.contracts import (
    ContractError,
    parse_compare,
    parse_query,
    parse_traffic_quality,
    schema_document,
)
from apps.api.v1.execution import analytics_transaction
from apps.api.v1.queries import dimension_values
from apps.api.v1.services import QueryLimitError, run_compare, run_query, run_traffic_quality
from apps.common.json_views import JSONView, json_response
from apps.common.mixins import ApiAuthMixin
from apps.core.models import Website


@method_decorator(csrf_exempt, name="dispatch")
class V1AuthenticatedView(ApiAuthMixin, JSONView):
    """Bearer-authenticated v1 base whose POST handlers do not use cookie CSRF."""


class CapabilitiesView(V1AuthenticatedView):
    """Return API v1 operations and limits without running analytics SQL."""

    http_method_names = ("get",)

    def get(self, request: HttpRequest) -> JsonResponse:
        return json_response(capabilities())


class SchemaView(V1AuthenticatedView):
    """Return the stable request schema document."""

    http_method_names = ("get",)

    def get(self, request: HttpRequest) -> JsonResponse:
        return json_response(schema_document())


class AnalyticsQueryView(V1AuthenticatedView):
    """Execute a metrics, breakdown, or time-series query."""

    http_method_names = ("post",)

    def post(self, request: HttpRequest) -> JsonResponse:
        return _execute(request, parse_query, run_query)


class AnalyticsCompareView(V1AuthenticatedView):
    """Execute a complete period comparison before ranking and limiting."""

    http_method_names = ("post",)

    def post(self, request: HttpRequest) -> JsonResponse:
        return _execute(request, parse_compare, run_compare)


class TrafficQualityView(V1AuthenticatedView):
    """Return transparent traffic-quality measures and indicators."""

    http_method_names = ("post",)

    def post(self, request: HttpRequest) -> JsonResponse:
        return _execute(request, parse_traffic_quality, run_traffic_quality)


class DimensionValuesView(V1AuthenticatedView):
    """Discover bounded dimension values under the supplied filters."""

    http_method_names = ("post",)

    def post(self, request: HttpRequest) -> JsonResponse:
        try:
            body = _json_body(request)
            dimension = str(body.get("dimension") or "")
            query_body = dict(body)
            query_body["operation"] = "breakdown"
            query_body["dimensions"] = [dimension]
            query_body["metrics"] = ["events" if dimension == "event_name" else "pageviews"]
            spec = parse_query(query_body)
            forbidden = _website_error(request, spec.website_id)
            if forbidden:
                return forbidden
            with analytics_transaction():
                rows = dimension_values(spec, dimension, body.get("search"))
            return json_response(
                {
                    "schema_version": "1",
                    "query": spec.query_metadata(),
                    "comparison": None,
                    "totals": {},
                    "rows": rows,
                }
            )
        except ContractError as exc:
            return json_response({"error": exc.as_dict()}, status=400)
        except (OperationalError, DatabaseError):
            return json_response(
                {"error": {"code": "QUERY_FAILED", "message": "Analytics query failed."}},
                status=503,
            )


def _execute(request: HttpRequest, parser: Any, service: Any) -> JsonResponse:
    try:
        body = _json_body(request)
        spec = parser(body)
        website_id = spec.query.website_id if hasattr(spec, "query") else spec.website_id
        forbidden = _website_error(request, website_id)
        if forbidden:
            return forbidden
        with analytics_transaction():
            result = service(spec)
        return json_response(result)
    except ContractError as exc:
        return json_response({"error": exc.as_dict()}, status=400)
    except QueryLimitError as exc:
        return json_response(
            {"error": {"code": "QUERY_LIMIT_EXCEEDED", "message": str(exc)}},
            status=422,
        )
    except (OperationalError, DatabaseError):
        return json_response(
            {"error": {"code": "QUERY_FAILED", "message": "Analytics query failed."}},
            status=503,
        )


def _json_body(request: HttpRequest) -> dict[str, Any]:
    try:
        value = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ContractError("invalid JSON body", code="INVALID_JSON") from exc
    if not isinstance(value, dict):
        raise ContractError("request body must be a JSON object")
    return value


def _website_error(request: HttpRequest, website_id: str) -> JsonResponse | None:
    queryset = Website.objects.filter(id=website_id, is_deleted=False)
    if "admin" not in getattr(request, "api_key_scopes", []):
        queryset = queryset.filter(user_id=request.api_user_id)
    if not queryset.exists():
        return json_response(
            {"error": {"code": "WEBSITE_NOT_ACCESSIBLE", "message": "Website not accessible."}},
            status=403,
        )
    return None
