"""Authlib grants with transaction-safe, opaque Django storage."""

import copy
import json
import logging
import re
import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

from authlib.integrations.django_oauth2 import AuthorizationServer
from authlib.oauth2.rfc6749 import InvalidGrantError, OAuth2Error
from authlib.oauth2.rfc6749.grants import AuthorizationCodeGrant, RefreshTokenGrant
from authlib.oauth2.rfc7636 import CodeChallenge
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.test import RequestFactory
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.ai_connections.client_metadata import fetch_metadata, registration
from apps.ai_connections.models import AIConnection, OAuthClient, OAuthCredential
from apps.ai_connections.policy import (
    NOTICE,
    NOTICE_HASH,
    NOTICE_VERSION,
    SCOPES,
    AccessDenied,
    activity,
    available_sites,
    create_connection,
    digest,
    issue,
    limit,
    live_connection,
    lookup,
    public_origin,
    require_enabled,
    resource,
    revoke_locked,
    scopes,
    validate_grant,
)
from apps.tracker.ip import get_client_ip


def no_store(response):
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def error(code, status=400):
    return no_store(JsonResponse({"error": code}, status=status))


def public_request(request):
    require_enabled()
    if not settings.DEBUG and not request.is_secure():
        raise AccessDenied("insecure_transport")
    if (
        len(request.body) + len(request.META.get("QUERY_STRING", "").encode())
        > settings.AI_MAX_REQUEST_BYTES
    ):
        raise AccessDenied("invalid_request")
    peer = request.META.get("REMOTE_ADDR", "")
    # Reuse the hardened resolver only for an operator-declared topology.
    # The legacy count=0 mode trusts spoofable headers and is unsafe for quotas.
    if settings.TRUST_PROXY_HEADERS and settings.TRUSTED_PROXY_COUNT > 0:
        peer = get_client_ip(request)
    limit("public:" + digest(peer, "rate"), 60)


def single_parameters(request):
    if any(len(q.getlist(k)) != 1 for q in (request.GET, request.POST) for k in q):
        raise AccessDenied("invalid_request")
    if set(request.GET) & set(request.POST):
        raise AccessDenied("invalid_request")


def credential_for_grant(raw, kind, client_id):
    """All mutations lock the connection before its credential (no lock inversion)."""
    row = lookup(raw, kind)
    if row is None or row.connection_id is None:
        return None
    try:
        conn = live_connection(row.connection_id, lock=True)
    except AccessDenied:
        return None
    if conn.client_id != client_id or row.payload.get("resource") != resource():
        return None
    row = OAuthCredential.objects.select_for_update().filter(pk=row.pk).first()
    if row is None or row.expires_at <= timezone.now():
        return None
    if row.consumed_at:
        revoke_locked(conn)
        return None
    row.connection = conn
    return row


class S256Challenge(CodeChallenge):
    SUPPORTED_CODE_CHALLENGE_METHOD = ["S256"]
    DEFAULT_CODE_CHALLENGE_METHOD = "S256"


class CodeGrant(AuthorizationCodeGrant):
    TOKEN_ENDPOINT_AUTH_METHODS = ["none"]

    def generate_authorization_code(self):
        return "mai_" + secrets.token_urlsafe(48)

    def save_authorization_code(self, raw, request):
        selected_scopes = scopes(request.scope.split())
        selected_sites = request._request.ai_granted_sites
        conn = create_connection(
            request.user,
            request.client,
            "oauth",
            selected_sites,
            selected_scopes,
            timedelta(minutes=5),
        )
        issue(
            "code",
            {
                "resource": resource(),
                "redirect_uri": request.payload.redirect_uri,
                "scopes": selected_scopes,
                "code_challenge": request.payload.data["code_challenge"],
            },
            timedelta(minutes=5),
            conn,
            raw=raw,
        )
        activity(conn, "connection.authorize")

    def query_authorization_code(self, raw, client):
        return credential_for_grant(raw, "code", client.client_id)

    def authenticate_user(self, credential):
        return live_connection(credential.connection_id, lock=True).user

    def delete_authorization_code(self, credential):
        credential.consumed_at = timezone.now()
        credential.save(update_fields=["consumed_at"])


class RefreshGrant(RefreshTokenGrant):
    TOKEN_ENDPOINT_AUTH_METHODS = ["none"]
    INCLUDE_NEW_REFRESH_TOKEN = True

    def authenticate_refresh_token(self, raw):
        return credential_for_grant(raw, "refresh", self.request.client.client_id)

    def authenticate_user(self, credential):
        return live_connection(credential.connection_id, lock=True).user

    def revoke_old_credential(self, credential):
        credential.consumed_at = timezone.now()
        credential.save(update_fields=["consumed_at"])


class Server(AuthorizationServer):
    def create_oauth2_request(self, request):
        # Validate transport at the boundary; use the configured authority, not
        # a request-supplied Host. Authlib's HTTPS check stays on in production.
        normalized = copy.copy(request)
        normalized.META = dict(request.META)
        normalized.META["HTTP_HOST"] = urlsplit(public_origin()).netloc
        normalized.META["wsgi.url_scheme"] = "https"
        if hasattr(normalized, "environ"):
            normalized.environ = normalized.META
        if hasattr(normalized, "scope"):
            normalized.scope = {**normalized.scope, "scheme": "https"}
        normalized.__dict__.pop("_current_scheme_host", None)
        return super().create_oauth2_request(normalized)

    def save_token(self, token, request):
        original = request.authorization_code or request.refresh_token
        conn = live_connection(original.connection_id, lock=True)
        granted = sorted(set((token.get("scope") or "").split()) & set(conn.scopes))
        if not granted:
            raise InvalidGrantError()
        token["scope"] = " ".join(granted)
        expiry = timezone.now() + timedelta(days=30)
        conn.expires_at = expiry
        conn.save(update_fields=["expires_at"])
        payload = {"resource": resource(), "scopes": granted}
        issue("access", payload, timedelta(minutes=15), conn, raw=token["access_token"])
        issue("refresh", payload, timedelta(days=30), conn, raw=token["refresh_token"])


def server():
    logging.getLogger("authlib").setLevel(logging.CRITICAL + 1)
    logging.getLogger("authlib").propagate = False
    instance = Server(OAuthClient, OAuthCredential)
    instance.load_config(
        {
            "scopes_supported": list(SCOPES),
            "access_token_generator": lambda **kw: "mai_" + secrets.token_urlsafe(48),
            "refresh_token_generator": lambda **kw: "mai_" + secrets.token_urlsafe(48),
            "token_expires_in": {"authorization_code": 900, "refresh_token": 900},
        }
    )
    instance.register_grant(CodeGrant, [S256Challenge(required=True)])
    instance.register_grant(RefreshGrant)
    return instance


@require_GET
def authorization_metadata(request):
    try:
        require_enabled()
        origin = public_origin()
        return no_store(
            JsonResponse(
                {
                    "issuer": origin,
                    "authorization_endpoint": origin + "/oauth/authorize/",
                    "token_endpoint": origin + "/oauth/token/",
                    "registration_endpoint": origin + "/oauth/register/",
                    "revocation_endpoint": origin + "/oauth/revoke/",
                    "response_types_supported": ["code"],
                    "grant_types_supported": ["authorization_code", "refresh_token"],
                    "code_challenge_methods_supported": ["S256"],
                    "token_endpoint_auth_methods_supported": ["none"],
                    "client_id_metadata_document_supported": True,
                    "authorization_response_iss_parameter_supported": True,
                    "scopes_supported": list(SCOPES),
                }
            )
        )
    except AccessDenied as exc:
        return error(exc.code, 404)


@require_GET
def resource_metadata(request):
    try:
        require_enabled()
        return no_store(
            JsonResponse(
                {
                    "resource": resource(),
                    "authorization_servers": [public_origin()],
                    "scopes_supported": list(SCOPES),
                    "bearer_methods_supported": ["header"],
                }
            )
        )
    except AccessDenied as exc:
        return error(exc.code, 404)


@csrf_exempt
@require_POST
def register(request):
    try:
        public_request(request)
        data = json.loads(request.body)
        name, redirects = registration(data)
        client = OAuthClient.objects.create(
            client_id=secrets.token_urlsafe(32), name=name, redirect_uris=redirects
        )
        return no_store(
            JsonResponse(
                {
                    "client_id": client.pk,
                    "client_name": name,
                    "redirect_uris": redirects,
                    "token_endpoint_auth_method": "none",
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                },
                status=201,
            )
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        return error("invalid_client_metadata")
    except AccessDenied as exc:
        return error(exc.code, 429 if exc.code == "rate_limited" else 400)


@require_GET
def authorize(request):
    try:
        public_request(request)
        single_parameters(request)
        params = request.GET.dict()
        if (
            params.get("resource") != resource()
            or params.get("code_challenge_method") != "S256"
            or not re.fullmatch(r"[A-Za-z0-9_-]{43}", params.get("code_challenge", ""))
            or not params.get("state")
            or len(params["state"]) > 2048
            or not params.get("redirect_uri")
        ):
            raise AccessDenied("invalid_request")
        client_id = params.get("client_id", "")
        if len(client_id) > 2048:
            raise AccessDenied("invalid_client")
        if client_id.startswith("https://"):
            name, redirects = fetch_metadata(client_id)
            OAuthClient.objects.update_or_create(
                client_id=client_id, defaults={"name": name, "redirect_uris": redirects}
            )
        server().get_consent_grant(request)
        nonce = request.session.get("ai_consent_nonce") or secrets.token_urlsafe(32)
        request.session["ai_consent_nonce"] = nonce
        payload = {
            **params,
            "scope": params.get("scope", "sites:read analytics:read"),
            "browser": digest(nonce, "browser"),
            "initiating_user": str(request.user.pk) if request.user.is_authenticated else None,
            "notice_hash": NOTICE_HASH,
        }
        request_id = issue("request", payload, timedelta(minutes=10))
        return no_store(
            HttpResponseRedirect(
                "/settings/ai-connections/consent/?" + urlencode({"request_id": request_id})
            )
        )
    except AccessDenied as exc:
        return error(exc.code, 429 if exc.code == "rate_limited" else 400)
    except OAuth2Error as exc:
        return error(exc.error)


def pending(request, lock=False):
    raw = (
        request.GET.get("request_id") if request.method == "GET" else request.POST.get("request_id")
    )
    row = lookup(raw, "request")
    if row and lock:
        row = OAuthCredential.objects.select_for_update().filter(pk=row.pk).first()
    nonce = request.session.get("ai_consent_nonce", "")
    if (
        not row
        or row.consumed_at
        or row.expires_at <= timezone.now()
        or not nonce
        or row.payload.get("browser") != digest(nonce, "browser")
        or row.payload.get("initiating_user") not in (None, str(request.user.pk))
    ):
        raise AccessDenied("invalid_request")
    return row, raw


@login_required
def consent(request):
    if request.method not in ("GET", "POST"):
        return error("invalid_request", 405)
    try:
        require_enabled()
        if request.method == "GET":
            row, raw = pending(request)
            client = OAuthClient.objects.get(pk=row.payload["client_id"])
            requested = scopes(row.payload["scope"].split())
            return no_store(
                render(
                    request,
                    "ai_connections/consent.html",
                    {
                        "request_id": raw,
                        "client_name": client.name,
                        "client_host": urlsplit(row.payload["redirect_uri"]).netloc,
                        "requested_scopes": [(s, SCOPES[s]) for s in requested],
                        "sites": available_sites(request.user),
                        "notice": _(NOTICE),
                        "notice_version": NOTICE_VERSION,
                        "notice_hash": NOTICE_HASH,
                    },
                )
            )
        with transaction.atomic():
            row, _request_id = pending(request, lock=True)
            if (
                row.payload.get("notice_hash") != NOTICE_HASH
                or request.POST.get("notice_hash") != NOTICE_HASH
                or request.POST.get("notice_version") != NOTICE_VERSION
            ):
                raise AccessDenied("notice_changed")
            approved = request.POST.get("approve") == "yes"
            params = {
                k: v
                for k, v in row.payload.items()
                if k not in ("browser", "notice_hash", "initiating_user")
            }
            selected_sites = []
            if approved:
                if request.POST.get("acknowledged") != "yes":
                    raise AccessDenied("consent_required")
                selected_sites, selected_scopes = validate_grant(
                    request.user, request.POST.getlist("sites"), request.POST.getlist("scopes")
                )
                if not set(selected_scopes) <= set(row.payload["scope"].split()):
                    raise AccessDenied()
                params["scope"] = " ".join(selected_scopes)
            internal = RequestFactory().get(
                public_origin() + "/oauth/authorize/", params, secure=True
            )
            internal.ai_granted_sites = selected_sites
            response = server().create_authorization_response(
                internal, grant_user=request.user if approved else None
            )
            if response.status_code == 302:
                separator = "&" if "?" in response["Location"] else "?"
                response["Location"] += separator + urlencode({"iss": public_origin()})
                row.consumed_at = timezone.now()
                row.save(update_fields=["consumed_at"])
            return no_store(response)
    except (AccessDenied, OAuthClient.DoesNotExist) as exc:
        return no_store(
            render(
                request,
                "ai_connections/consent_error.html",
                {"code": getattr(exc, "code", "invalid_request")},
                status=400,
            )
        )
    except OAuth2Error as exc:
        return error(exc.error)


@csrf_exempt
@require_POST
def token(request):
    try:
        public_request(request)
        single_parameters(request)
        if request.GET or request.POST.get("resource") != resource():
            raise AccessDenied("invalid_target")
        with transaction.atomic():
            response = server().create_token_response(request)
        return no_store(response)
    except AccessDenied as exc:
        return error(exc.code, 429 if exc.code == "rate_limited" else 400)
    except OAuth2Error as exc:
        return error(exc.error)


@csrf_exempt
@require_POST
def revoke_token(request):
    try:
        public_request(request)
        single_parameters(request)
        raw, client_id = request.POST.get("token", ""), request.POST.get("client_id", "")
        credential = lookup(raw, "refresh") or lookup(raw, "access")
        if credential:
            with transaction.atomic():
                conn = (
                    AIConnection.objects.select_for_update()
                    .filter(pk=credential.connection_id)
                    .first()
                )
                # Offline cleanup may delete the family after credential lookup.
                # Unknown/already-removed tokens retain RFC 7009's no-op success.
                if conn is not None and conn.client_id == client_id:
                    revoke_locked(conn)
        return no_store(JsonResponse({}))
    except AccessDenied as exc:
        return error(exc.code, 400)
