"""Cookie/CSRF-protected connection management. Never accepts MCP bearer identity."""

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_POST

from apps.ai_connections.models import AIActivity, AIConnection, OAuthClient
from apps.ai_connections.oauth import error, no_store
from apps.ai_connections.policy import (
    NOTICE,
    NOTICE_HASH,
    NOTICE_VERSION,
    SCOPES,
    AccessDenied,
    activity,
    available_sites,
    create_connection,
    fingerprint,
    issue,
    reduce_owned,
    require_enabled,
    resource,
    revoke_owned,
)
from apps.ai_connections.providers import PROVIDERS, agent_prompt, claude_url

PAGE_SIZE = 10
ACTIONS = {
    "list_sites": _("Listed approved sites"),
    "describe_analytics": _("Read analytics capabilities"),
    "get_connection_status": _("Verified connection"),
    "query_metrics": _("Read statistics"),
    "query_timeseries": _("Read time series"),
    "compare_breakdown": _("Compared periods"),
    "traffic_quality": _("Read traffic diagnostics"),
    "list_dimension_values": _("Listed dimension values"),
    "connection.authorize": _("Authorized connection"),
    "connection.token": _("Created personal token"),
    "connection.revoke": _("Revoked connection"),
    "connection.reduce": _("Reduced access"),
}


def paginate(query, user, purpose, cursor):
    if cursor:
        try:
            data = signing.loads(cursor, salt=purpose, max_age=90 * 86400)
            if data["user"] != str(user.pk):
                raise ValueError()
            query = query.filter(
                Q(created_at__lt=data["time"]) | Q(created_at=data["time"], id__lt=data["id"])
            )
        except (signing.BadSignature, KeyError, ValueError, TypeError):
            raise AccessDenied("invalid_cursor") from None
    rows = list(query.order_by("-created_at", "-id")[: PAGE_SIZE + 1])
    next_cursor = ""
    if len(rows) > PAGE_SIZE:
        last = rows[PAGE_SIZE - 1]
        next_cursor = signing.dumps(
            {"user": str(user.pk), "time": last.created_at.isoformat(), "id": str(last.pk)},
            salt=purpose,
        )
    return rows[:PAGE_SIZE], next_cursor


def state(conn, user):
    if conn.revoked_at:
        return "revoked", _("Revoked")
    if conn.expires_at <= timezone.now():
        return "expired", _("Expired")
    if not user.is_active or conn.auth_fingerprint != fingerprint(user):
        return "invalidated", _("Invalidated after account change")
    if conn.verified_at:
        return "verified", _("Verified")
    return "authorized", _("Authorized, not verified yet")


def page_context(request, new_token=None):
    user = request.user
    websites = available_sites(user)
    website_map = {w["id"]: w for w in websites}
    queryset = AIConnection.objects.filter(user=user)
    valid = Q(
        revoked_at__isnull=True, expires_at__gt=timezone.now(), auth_fingerprint=fingerprint(user)
    )
    counts = queryset.aggregate(
        total=Count("pk"),
        verified=Count("pk", filter=valid & Q(verified_at__isnull=False)),
        authorized=Count("pk", filter=valid & Q(verified_at__isnull=True)),
    )
    counts["inactive"] = counts["total"] - counts["verified"] - counts["authorized"]
    try:
        endpoint = resource()
    except AccessDenied:
        endpoint = ""
    enabled = settings.AI_CONNECTIONS_ENABLED and bool(endpoint)
    tab = request.GET.get("tab", "connect")
    if tab not in ("connect", "connections", "activity"):
        tab = "connect"
    rows, next_cursor = [], ""
    operations = []
    if tab == "connections":
        connections, next_cursor = paginate(
            queryset.select_related("client"), user, "ai-connections", request.GET.get("cursor", "")
        )
        for conn in connections:
            code, label = state(conn, user)
            rows.append(
                {
                    "id": conn.pk,
                    "name": conn.client.name,
                    "method": conn.get_auth_method_display(),
                    "state": code,
                    "state_label": label,
                    "active": code in ("verified", "authorized"),
                    "scopes": [(s, SCOPES[s]) for s in conn.scopes],
                    "sites": [
                        {
                            "id": site_id,
                            "name": website_map.get(site_id, {}).get(
                                "name", _("Site no longer accessible")
                            ),
                        }
                        for site_id in conn.website_ids
                    ],
                    "expires_at": conn.expires_at,
                    "last_used_at": conn.last_used_at,
                }
            )
    if tab == "activity":
        query = AIActivity.objects.filter(
            user=user,
            created_at__gte=timezone.now() - timedelta(days=settings.AI_AUDIT_RETENTION_DAYS),
        ).select_related("connection__client")
        records, next_cursor = paginate(query, user, "ai-activity", request.GET.get("cursor", ""))
        operations = [
            {
                "name": row.connection.client.name,
                "action": ACTIONS.get(row.action, _("Connection operation")),
                "outcome": _("Completed") if row.outcome == "success" else _("Not completed"),
                "code": row.outcome,
                "time": row.created_at,
            }
            for row in records
        ]
    return {
        "tab": tab,
        "counts": counts,
        "connections": rows,
        "operations": operations,
        "next_cursor": next_cursor,
        "websites": websites,
        "selected_website": "",
        "scope_choices": list(SCOPES.items()),
        "enabled": enabled,
        "endpoint": endpoint,
        "claude_url": claude_url(endpoint) if enabled else "",
        "providers": PROVIDERS,
        "agent_prompt": agent_prompt(endpoint),
        "new_token": new_token,
        "notice": _(NOTICE),
        "notice_hash": NOTICE_HASH,
        "notice_version": NOTICE_VERSION,
    }


@login_required
@require_GET
def index(request):
    try:
        return no_store(render(request, "settings/ai_connections.html", page_context(request)))
    except AccessDenied as exc:
        return error(exc.code)


@login_required
@require_POST
def create_personal_token(request):
    try:
        require_enabled()
        if (
            request.POST.get("acknowledged") != "yes"
            or request.POST.get("notice_hash") != NOTICE_HASH
            or request.POST.get("notice_version") != NOTICE_VERSION
        ):
            raise AccessDenied("consent_required")
        name = request.POST.get("name", "").strip()
        if not name or len(name) > 120 or any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise AccessDenied("invalid_name")
        try:
            days = int(request.POST.get("days", "30"))
        except ValueError:
            raise AccessDenied("invalid_expiry") from None
        if not 1 <= days <= 90:
            raise AccessDenied("invalid_expiry")
        with transaction.atomic():
            client = OAuthClient.objects.create(
                client_id="personal:" + secrets.token_urlsafe(32), name=name, redirect_uris=[]
            )
            conn = create_connection(
                request.user,
                client,
                "personal",
                request.POST.getlist("sites"),
                request.POST.getlist("scopes"),
                timedelta(days=days),
            )
            raw = issue(
                "personal",
                {"resource": resource(), "scopes": conn.scopes},
                timedelta(days=days),
                conn,
            )
            activity(conn, "connection.token")
        return no_store(
            render(
                request,
                "settings/ai_connections.html",
                page_context(request, {"token": raw, "name": name, "expires_at": conn.expires_at}),
            )
        )
    except AccessDenied as exc:
        return no_store(
            render(
                request,
                "settings/ai_connections.html",
                {**page_context(request), "action_error": exc.code},
                status=400,
            )
        )


@login_required
@require_POST
def revoke(request, connection_id):
    try:
        revoke_owned(request.user, connection_id)
        return no_store(HttpResponseRedirect("/settings/ai-connections/?tab=connections"))
    except AIConnection.DoesNotExist:
        return error("not_found", 404)


@login_required
@require_POST
def reduce(request, connection_id):
    try:
        reduce_owned(
            request.user,
            connection_id,
            request.POST.getlist("sites"),
            request.POST.getlist("scopes"),
        )
        return no_store(HttpResponseRedirect("/settings/ai-connections/?tab=connections"))
    except AIConnection.DoesNotExist:
        return error("not_found", 404)
    except AccessDenied as exc:
        return error(exc.code)
