"""Canonical identity, immutable grants and per-call access checks."""

import hashlib
import hmac
import ipaddress
import re
import secrets
import threading
import time
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop

from apps.ai_connections.models import AIActivity, AIConnection, OAuthCredential
from apps.analytics.services import resolve_websites_for_user
from apps.core.models import MantecatoUser

SCOPES = {"sites:read": _("List approved sites"), "analytics:read": _("Read aggregate analytics")}
NOTICE_VERSION = "ai-connections-1"
NOTICE = gettext_noop(
    "Allow this client to read aggregate analytics for selected sites. Paths, titles and event "
    "names can contain personal data. Results may be retained by the external service. "
    "Revocation prevents future access but cannot recall copies already received. "
    "No administration or write access is granted."
)
NOTICE_HASH = hashlib.sha256(NOTICE.encode()).hexdigest()


class AccessDenied(ValueError):
    def __init__(self, code="permission_denied"):
        self.code = code
        super().__init__(code)


def public_origin():
    value = settings.MANTECATO_PUBLIC_URL
    try:
        p = urlsplit(value)
        loopback = p.hostname in ("localhost", "127.0.0.1", "::1")
        valid = (
            p.hostname
            and not p.username
            and not p.password
            and not p.query
            and not p.fragment
            and p.path in ("", "/")
            and p.port != 0
            and (p.scheme == "https" or (settings.DEBUG and p.scheme == "http" and loopback))
            and not any(c.isspace() or c == "\\" for c in value)
        )
    except ValueError:
        valid = False
    if not valid:
        raise AccessDenied("public_endpoint_required")
    try:
        if len(value) > 2048:
            raise ValueError()
        if not (settings.DEBUG and loopback):
            validate_redirect(value.rstrip("/") + "/mcp")
        host = p.hostname.lower().encode("idna").decode("ascii")
    except (ValueError, AccessDenied):
        raise AccessDenied("public_endpoint_required") from None
    if ":" in host:
        host = "[" + host + "]"
    port = p.port
    if port and port != (443 if p.scheme == "https" else 80):
        host += ":" + str(port)
    return p.scheme + "://" + host


def resource():
    return public_origin() + "/mcp"


def digest(raw, kind):
    return hmac.new(
        settings.SECRET_KEY.encode(), ("ai:" + kind + ":" + raw).encode(), hashlib.sha256
    ).hexdigest()


def fingerprint(user):
    return digest(user.get_session_auth_hash(), "user")


def scopes(values):
    if not isinstance(values, list) or any(
        not isinstance(x, str) or x not in SCOPES for x in values
    ):
        raise AccessDenied("invalid_scope")
    return sorted(set(values))


def sites(values):
    if not isinstance(values, list) or len(values) > 500:
        raise AccessDenied("invalid_sites")
    try:
        return sorted({str(UUID(x)) for x in values})
    except (ValueError, TypeError, AttributeError):
        raise AccessDenied("invalid_sites") from None


def available_sites(user, website_ids=None):
    return (
        resolve_websites_for_user(str(user.pk), user.is_staff, website_ids)
        if user.is_active
        else []
    )


def validate_grant(user, selected, selected_scopes):
    selected = sites(selected)
    selected_scopes = scopes(selected_scopes)
    allowed = {w["id"] for w in available_sites(user)}
    if not selected or not selected_scopes or not set(selected) <= allowed:
        raise AccessDenied()
    return selected, selected_scopes


def create_connection(user, client, method, selected_sites, selected_scopes, lifetime):
    """Caller owns an atomic transaction; serialize quota checks on the user."""
    if lifetime is None and method != "personal":
        raise AccessDenied("invalid_expiry")
    fresh = MantecatoUser.objects.select_for_update().get(pk=user.pk)
    if not fresh.is_active or not hmac.compare_digest(fingerprint(fresh), fingerprint(user)):
        raise AccessDenied("authentication_required")
    selected_sites, selected_scopes = validate_grant(fresh, selected_sites, selected_scopes)
    now = timezone.now()
    if (
        AIConnection.objects.filter(
            Q(expires_at__gt=now) | Q(auth_method="personal", expires_at__isnull=True),
            user=fresh,
            revoked_at__isnull=True,
            auth_fingerprint=fingerprint(fresh),
        ).count()
        >= settings.AI_MAX_ACTIVE_CONNECTIONS
    ):
        raise AccessDenied("connection_limit")
    return AIConnection.objects.create(
        user=fresh,
        client=client,
        auth_method=method,
        scopes=selected_scopes,
        website_ids=selected_sites,
        authorized_scopes=selected_scopes,
        authorized_websites=selected_sites,
        auth_fingerprint=fingerprint(fresh),
        notice_version=NOTICE_VERSION,
        notice_hash=NOTICE_HASH,
        expires_at=now + lifetime if lifetime is not None else None,
    )


def validate_redirect(uri):
    if (
        not isinstance(uri, str)
        or len(uri) > 2048
        or any(c.isspace() or c == "\\" or ord(c) < 32 or ord(c) == 127 for c in uri)
    ):
        raise AccessDenied("invalid_redirect_uri")
    try:
        p = urlsplit(uri)
        loopback = p.hostname in ("localhost", "127.0.0.1", "::1")
        if (
            not p.hostname
            or p.username
            or p.password
            or p.fragment
            or p.port == 0
            or not (p.scheme == "https" or (p.scheme == "http" and loopback))
            or set(parse_qs(p.query, keep_blank_values=True)) & {"code", "state", "iss", "error"}
        ):
            raise ValueError()
        if p.scheme == "https":
            hostname = p.hostname.rstrip(".").encode("idna").decode("ascii")
            if (
                not all(
                    re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
                    for label in hostname.split(".")
                )
                and ":" not in hostname
            ):
                raise ValueError()
            try:
                if not ipaddress.ip_address(p.hostname).is_global:
                    raise ValueError()
            except ValueError as exc:
                if ":" in p.hostname or p.hostname.replace(".", "").isdigit():
                    raise exc
                if hostname == "localhost" or hostname.endswith(
                    (".local", ".internal", ".localhost")
                ):
                    raise exc
    except ValueError:
        raise AccessDenied("invalid_redirect_uri") from None
    return uri


def issue(kind, payload, lifetime, connection=None, raw=None):
    if lifetime is None and (
        kind != "personal"
        or connection is None
        or connection.auth_method != "personal"
        or connection.expires_at is not None
    ):
        raise AccessDenied("invalid_expiry")
    raw = raw or ("mai_" + secrets.token_urlsafe(48))
    OAuthCredential.objects.create(
        digest=digest(raw, kind),
        kind=kind,
        payload=payload,
        connection=connection,
        expires_at=timezone.now() + lifetime if lifetime is not None else None,
    )
    return raw


def lookup(raw, kind):
    if not isinstance(raw, str) or len(raw) > 256 or not raw.startswith("mai_"):
        return None
    return OAuthCredential.objects.filter(digest=digest(raw, kind), kind=kind).first()


def live_connection(connection_id, lock=False):
    public_origin()
    q = AIConnection.objects.select_related("user", "client")
    if lock:
        q = q.select_for_update(of=("self",))
    conn = q.filter(pk=connection_id).first()
    return validate_connection(conn)


def validate_connection(conn):
    if (
        conn is None
        or conn.revoked_at
        or conn.is_expired()
        or not conn.user.is_active
        or not hmac.compare_digest(conn.auth_fingerprint, fingerprint(conn.user))
    ):
        raise AccessDenied("authentication_required")
    return conn


def verify(raw):
    public_origin()
    if not isinstance(raw, str) or len(raw) > 256 or not raw.startswith("mai_"):
        raise AccessDenied("authentication_required")
    credential = (
        OAuthCredential.objects.select_related("connection__user", "connection__client")
        .filter(
            Q(kind="access", digest=digest(raw, "access"))
            | Q(kind="personal", digest=digest(raw, "personal"))
        )
        .first()
    )
    if not credential or credential.is_expired() or credential.consumed_at:
        raise AccessDenied("authentication_required")
    conn = validate_connection(credential.connection)
    if credential.payload.get("resource") != resource():
        raise AccessDenied("authentication_required")
    if (credential.kind == "personal") != (conn.auth_method == "personal"):
        raise AccessDenied("authentication_required")
    return credential, conn, sorted(set(conn.scopes) & set(credential.payload.get("scopes", [])))


def authorize(raw, scope=None, website_id=None):
    credential, conn, granted = verify(raw)
    if scope and scope not in granted:
        raise AccessDenied()
    allowed = {w["id"] for w in available_sites(conn.user, conn.website_ids)}
    if website_id and website_id not in allowed:
        raise AccessDenied()
    return credential, conn, granted, allowed


def activity(conn, action, outcome="success", website_id=None):
    AIActivity.objects.create(
        user_id=conn.user_id, connection=conn, action=action, outcome=outcome, website_id=website_id
    )


def mark_verified(raw):
    _, conn, _ = verify(raw)
    now = timezone.now()
    if conn.verified_at is None:
        AIConnection.objects.filter(pk=conn.pk, verified_at__isnull=True).update(verified_at=now)
    if conn.last_used_at is None:
        AIConnection.objects.filter(pk=conn.pk, last_used_at__isnull=True).update(last_used_at=now)
    elif conn.last_used_at <= now - timedelta(seconds=60):
        AIConnection.objects.filter(
            pk=conn.pk, last_used_at__lte=now - timedelta(seconds=60)
        ).update(last_used_at=now)


def revoke_locked(conn):
    if conn.revoked_at is None:
        conn.revoked_at = timezone.now()
        conn.save(update_fields=["revoked_at"])
        OAuthCredential.objects.filter(connection=conn).delete()
        activity(conn, "connection.revoke")


@transaction.atomic
def revoke_owned(user, connection_id):
    conn = AIConnection.objects.select_for_update().get(pk=connection_id, user=user)
    revoke_locked(conn)


@transaction.atomic
def reduce_owned(user, connection_id, selected_sites, selected_scopes):
    conn = AIConnection.objects.select_for_update().get(pk=connection_id, user=user)
    selected_sites, selected_scopes = sites(selected_sites), scopes(selected_scopes)
    if (
        conn.revoked_at
        or not set(selected_sites) <= set(conn.website_ids)
        or not set(selected_scopes) <= set(conn.scopes)
    ):
        raise AccessDenied()
    conn.website_ids, conn.scopes = selected_sites, selected_scopes
    conn.save(update_fields=["website_ids", "scopes"])
    activity(conn, "connection.reduce")


_rate_lock = threading.Lock()
_rate = {}


def limit(key, maximum=30):
    """Bounded, explicitly per-worker best-effort limiter, not a global quota."""
    now = time.monotonic()
    with _rate_lock:
        start, count = _rate.get(key, (now, 0))
        if now - start >= 60:
            start, count = now, 0
        if count >= maximum:
            raise AccessDenied("rate_limited")
        if len(_rate) >= 4096 and key not in _rate:
            _rate.clear()
        _rate[key] = (start, count + 1)
