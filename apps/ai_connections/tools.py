"""Read-only adapters to the existing v1 contracts and bounded SQL services."""

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import DatabaseError

from apps.ai_connections.policy import (
    AccessDenied,
    activity,
    authorize,
    available_sites,
    limit,
    mark_verified,
)
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

TOOL_SCOPES = {
    "list_sites": "sites:read",
    "describe_analytics": None,
    "get_connection_status": None,
    "query_metrics": "analytics:read",
    "query_timeseries": "analytics:read",
    "compare_breakdown": "analytics:read",
    "traffic_quality": "analytics:read",
    "list_dimension_values": "analytics:read",
}


def execute(raw, name, body=None):
    """Audit contains only known tool/status/UUID; never exception text or values."""
    import json

    _, conn, granted, allowed = authorize(raw)
    site = None
    outcome = "unavailable"
    try:
        limit("tool:" + str(conn.pk))
        authorize(raw, TOOL_SCOPES[name])
        if name == "describe_analytics":
            result = {"capabilities": capabilities(), "schema": schema_document()}
        elif name == "get_connection_status":
            result = {
                "verified": True,
                "read_only": True,
                "scopes": granted,
                "approved_site_count": len(allowed),
                "expires_at": conn.expires_at.isoformat(),
            }
        elif name == "list_sites":
            result = {
                "websites": [
                    w for w in available_sites(conn.user, conn.website_ids) if w["id"] in allowed
                ]
            }
        else:
            body = dict(body or {})
            if name == "compare_breakdown":
                spec, service = parse_compare(body), run_compare
                site = spec.query.website_id
            elif name == "traffic_quality":
                spec, service = parse_traffic_quality(body), run_traffic_quality
                site = spec.query.website_id
            else:
                if name == "list_dimension_values":
                    dimension = body.get("dimension", "")
                    body.update(
                        operation="breakdown",
                        dimensions=[dimension],
                        metrics=["events" if dimension == "event_name" else "pageviews"],
                    )
                spec, service = parse_query(body), run_query
                site = spec.website_id
            authorize(raw, TOOL_SCOPES[name], site)
            with analytics_transaction():
                if name == "list_dimension_values":
                    result = {
                        "schema_version": "1",
                        "query": spec.query_metadata(),
                        "comparison": None,
                        "totals": {},
                        "rows": dimension_values(spec, dimension, body.get("search")),
                    }
                else:
                    result = service(spec)
        encoded = json.dumps(result, ensure_ascii=False, cls=DjangoJSONEncoder)
        if len(encoded.encode()) > settings.AI_MAX_RESPONSE_BYTES:
            raise AccessDenied("result_too_large")
        decoded = json.loads(encoded)
        authorize(raw, TOOL_SCOPES[name], site)
        mark_verified(raw)
        outcome = "success"
        return decoded
    except ContractError:
        outcome = "invalid_arguments"
        raise AccessDenied(outcome) from None
    except QueryLimitError:
        outcome = "query_limit_exceeded"
        raise AccessDenied(outcome) from None
    except DatabaseError:
        outcome = "unavailable"
        raise AccessDenied(outcome) from None
    except AccessDenied as exc:
        outcome = exc.code
        raise
    finally:
        if outcome != "rate_limited":
            activity(conn, name, outcome, site)


def base_query(website_id, range, start, end, timezone, filters, filter_groups):
    body = {
        "website_id": website_id,
        "range": range,
        "timezone": timezone,
        "filters": filters or [],
        "filter_groups": filter_groups or [],
    }
    if start is not None or end is not None:
        body.update(start=start, end=end)
    return body
