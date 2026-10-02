"""OAuth, tenant boundaries and secret lifecycle on isolated PostgreSQL."""

import json
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from django.db import IntegrityError, transaction
from django.test import Client, RequestFactory
from django.utils import timezone

from apps.ai_connections.models import AIActivity, AIConnection, OAuthClient, OAuthCredential
from apps.ai_connections.policy import (
    NOTICE_HASH,
    NOTICE_VERSION,
    AccessDenied,
    create_connection,
    issue,
    reduce_owned,
    resource,
    revoke_owned,
    verify,
)
from apps.ai_connections.tools import execute
from apps.core.models import MantecatoUser, Website, WebsiteEvent

pytestmark = pytest.mark.django_db


def test_provider_marks_are_local_small_and_passive():
    from pathlib import Path
    from xml.etree import ElementTree

    from apps.ai_connections.providers import PROVIDERS

    root = Path(__file__).resolve().parents[1] / "static"
    total = 0
    for provider in PROVIDERS:
        icon = provider["icon"]
        assert icon.startswith("images/providers/") and icon.endswith(".svg")
        data = (root / icon).read_bytes()
        total += len(data)
        svg = ElementTree.fromstring(data)
        assert svg.tag == "{http://www.w3.org/2000/svg}svg"
        for element in svg.iter():
            assert element.tag.split("}")[-1] not in ("script", "foreignObject", "image", "use")
            for attribute in element.attrib:
                assert not attribute.split("}")[-1].startswith("on")
                assert attribute.split("}")[-1] != "href"
    assert total < 12_288
    assert (root / "images/providers/LICENSE").exists()
    assert (root / "images/providers/README.md").exists()


@pytest.fixture(autouse=True)
def ai_settings(settings):
    settings.DEBUG = True
    settings.AI_CONNECTIONS_ENABLED = True
    settings.MANTECATO_PUBLIC_URL = "https://analytics.example.test"
    settings.SECURE_SSL_REDIRECT = False
    from apps.ai_connections.policy import _rate

    _rate.clear()


@pytest.fixture
def account():
    user = MantecatoUser.objects.create_user(username="owner", password="synthetic-password")
    site = Website.objects.create(user_id=user.pk, name="Example", domain="https://example.test")
    return user, site


@pytest.fixture
def browser(account):
    c = Client()
    c.force_login(account[0])
    return c


def personal(account, selected_scopes=None, lifetime=timedelta(days=30)):
    user, site = account
    with transaction.atomic():
        client = OAuthClient.objects.create(
            client_id="fixture-client", name="Synthetic client", redirect_uris=[]
        )
        conn = create_connection(
            user,
            client,
            "personal",
            [str(site.pk)],
            selected_scopes or ["sites:read", "analytics:read"],
            lifetime,
        )
        raw = issue("personal", {"resource": resource(), "scopes": conn.scopes}, lifetime, conn)
    return conn, raw


def start_flow(browser):
    result = browser.post(
        "/oauth/register/",
        json.dumps(
            {
                "client_name": "Synthetic client",
                "redirect_uris": ["https://client.example.test/callback"],
                "token_endpoint_auth_method": "none",
            }
        ),
        content_type="application/json",
    )
    assert result.status_code == 201, result.content
    client_id = result.json()["client_id"]
    verifier = "v" * 64
    response = browser.get(
        "/oauth/authorize/",
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "https://client.example.test/callback",
            "resource": resource(),
            "scope": "sites:read analytics:read",
            "state": "synthetic-state",
            "code_challenge_method": "S256",
            "code_challenge": create_s256_code_challenge(verifier),
        },
    )
    assert response.status_code == 302, response.content
    request_id = parse_qs(urlsplit(response["Location"]).query)["request_id"][0]
    return client_id, verifier, request_id


def approve(browser, account, request_id):
    response = browser.post(
        "/settings/ai-connections/consent/",
        {
            "request_id": request_id,
            "notice_hash": NOTICE_HASH,
            "notice_version": NOTICE_VERSION,
            "approve": "yes",
            "acknowledged": "yes",
            "sites": [str(account[1].pk)],
            "scopes": ["sites:read", "analytics:read"],
        },
    )
    assert response.status_code == 302, response.content
    params = parse_qs(urlsplit(response["Location"]).query)
    assert params["state"] == ["synthetic-state"]
    assert params["iss"] == ["https://analytics.example.test"]
    return params["code"][0]


def exchange(browser, client_id, verifier, code):
    return browser.post(
        "/oauth/token/",
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": "https://client.example.test/callback",
            "resource": resource(),
        },
    )


def test_real_oauth_code_refresh_and_no_plaintext_storage(browser, account):
    client_id, verifier, request_id = start_flow(browser)
    response = browser.get("/settings/ai-connections/consent/", {"request_id": request_id})
    assert response.status_code == 200 and b"Read-only permissions" in response.content
    code = approve(browser, account, request_id)
    response = exchange(browser, client_id, verifier, code)
    assert response.status_code == 200, response.content
    tokens = response.json()
    assert verify(tokens["access_token"])[1].verified_at is None
    refreshed = browser.post(
        "/oauth/token/",
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": tokens["refresh_token"],
            "resource": resource(),
        },
    )
    assert refreshed.status_code == 200, refreshed.content
    assert refreshed.json()["refresh_token"] != tokens["refresh_token"]
    stored = str(list(OAuthCredential.objects.values()))
    for raw in [
        code,
        tokens["access_token"],
        tokens["refresh_token"],
        refreshed.json()["access_token"],
    ]:
        assert raw not in stored
    replay = browser.post(
        "/oauth/token/",
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": tokens["refresh_token"],
            "resource": resource(),
        },
    )
    assert replay.status_code == 400
    assert AIConnection.objects.get().revoked_at is not None
    with pytest.raises(AccessDenied):
        verify(refreshed.json()["access_token"])


def test_bad_pkce_does_not_consume_valid_code(browser, account):
    client_id, verifier, request_id = start_flow(browser)
    code = approve(browser, account, request_id)
    assert exchange(browser, client_id, "x" * 64, code).status_code == 400
    assert exchange(browser, client_id, verifier, code).status_code == 200
    assert exchange(browser, client_id, verifier, code).status_code == 400
    assert AIConnection.objects.get().revoked_at


@pytest.mark.parametrize("change", ["resource", "scope", "client_id", "redirect_uri"])
def test_invalid_authorization_never_redirects(browser, change):
    result = browser.post(
        "/oauth/register/",
        json.dumps(
            {"client_name": "Test", "redirect_uris": ["https://client.example.test/callback"]}
        ),
        content_type="application/json",
    )
    values = {
        "response_type": "code",
        "client_id": result.json()["client_id"],
        "redirect_uri": "https://client.example.test/callback",
        "resource": resource(),
        "state": "ok",
        "scope": "sites:read",
        "code_challenge_method": "S256",
        "code_challenge": create_s256_code_challenge("v" * 64),
    }
    values[change] = "https://attacker.example.test/" if change != "scope" else "admin"
    response = browser.get("/oauth/authorize/", values)
    assert response.status_code == 400
    assert not AIConnection.objects.exists()


def test_consent_is_browser_bound_one_time_and_explicit(browser, account):
    _, _, request_id = start_flow(browser)
    other = Client()
    other.force_login(account[0])
    assert (
        other.get("/settings/ai-connections/consent/", {"request_id": request_id}).status_code
        == 400
    )
    assert (
        browser.post(
            "/settings/ai-connections/consent/",
            {
                "request_id": request_id,
                "approve": "yes",
                "notice_hash": NOTICE_HASH,
                "notice_version": NOTICE_VERSION,
            },
        ).status_code
        == 400
    )
    assert not AIConnection.objects.exists()
    approve(browser, account, request_id)
    assert (
        browser.get("/settings/ai-connections/consent/", {"request_id": request_id}).status_code
        == 400
    )


@pytest.mark.parametrize("days", ["30", "never", None])
def test_personal_token_show_once_and_csrf(browser, account, days):
    response = browser.post(
        "/settings/ai-connections/tokens/",
        {
            "name": "Desktop",
            **({"days": days} if days is not None else {}),
            "sites": [str(account[1].pk)],
            "scopes": ["sites:read"],
            "acknowledged": "yes",
            "notice_version": NOTICE_VERSION,
            "notice_hash": NOTICE_HASH,
        },
    )
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    raw = response.context["new_token"]["token"]
    assert response.context["tab"] == "connections"
    assert response.context["connections"][0]["name"] == "Desktop"
    assert response.context["connections"][0]["revocable"]
    credential, conn, _ = verify(raw)
    if days == "never":
        assert conn.expires_at is None and credential.expires_at is None
        assert b"Never expires" in response.content
    else:
        assert timedelta(days=29) < conn.expires_at - timezone.now() <= timedelta(days=30)
    assert raw.encode() in response.content
    assert b'hx-history="false"' in response.content
    assert raw.encode() not in browser.get("/settings/ai-connections/").content
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(account[0])
    assert strict.post("/settings/ai-connections/tokens/", {"name": "bad"}).status_code == 403
    assert browser.get("/api/sites/", HTTP_AUTHORIZATION="Bearer " + raw).status_code == 401


def test_no_expiry_survives_years_and_cleanup_then_revokes(browser, account):
    from apps.ai_connections.maintenance import cleanup

    conn, raw = personal(account, lifetime=None)
    future = timezone.now() + timedelta(days=3650)
    with patch("django.utils.timezone.now", return_value=future):
        assert not verify(raw)[0].is_expired()
        assert execute(raw, "get_connection_status")["expires_at"] is None
        assert cleanup(batch_size=1)["status"] == "completed"
        assert verify(raw)[1].pk == conn.pk
    page = browser.get("/settings/ai-connections/")
    assert page.context["tab"] == "connections"
    assert page.context["counts"]["verified"] == 1
    assert page.context["connections"][0]["revocable"]
    assert b"Never expires" in page.content and raw.encode() not in page.content
    assert browser.post(f"/settings/ai-connections/{conn.pk}/revoke/").status_code == 302
    assert not OAuthCredential.objects.filter(connection=conn).exists()
    with pytest.raises(AccessDenied):
        verify(raw)
    page = browser.get("/settings/ai-connections/")
    assert page.context["connections"][0]["state"] == "revoked"
    assert not page.context["connections"][0]["revocable"]


def test_no_expiry_credentials_are_removed_for_soft_deleted_owner(account):
    from apps.ai_connections.maintenance import cleanup

    conn, raw = personal(account, lifetime=None)
    account[0].deleted_at = timezone.now()
    account[0].save(update_fields=["deleted_at"])
    with pytest.raises(AccessDenied):
        verify(raw)
    result = cleanup(batch_size=1)
    assert result["deleted"]["credentials"] == result["deleted"]["connections"] == 1
    assert not AIConnection.objects.filter(pk=conn.pk).exists()


def test_no_expiry_is_counted_in_active_quota(browser, account, settings):
    settings.AI_MAX_ACTIVE_CONNECTIONS = 1
    personal(account, lifetime=None)
    response = browser.post(
        "/settings/ai-connections/tokens/",
        {
            "name": "Second token",
            "days": "never",
            "sites": [str(account[1].pk)],
            "scopes": ["sites:read"],
            "acknowledged": "yes",
            "notice_version": NOTICE_VERSION,
            "notice_hash": NOTICE_HASH,
        },
    )
    assert response.status_code == 400
    assert response.context["action_error"] == "connection_limit"
    assert AIConnection.objects.count() == OAuthClient.objects.count() == 1


@pytest.mark.parametrize("kind", ["access", "refresh", "code", "request"])
def test_non_personal_credentials_cannot_disable_expiry(account, kind):
    conn, _ = personal(account, lifetime=None)
    with pytest.raises(AccessDenied, match="invalid_expiry"):
        issue(kind, {}, None, conn)
    with transaction.atomic(), pytest.raises(AccessDenied, match="invalid_expiry"):
        create_connection(
            account[0], conn.client, "oauth", [str(account[1].pk)], ["sites:read"], None
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        OAuthCredential.objects.filter(connection=conn).update(kind=kind)
    with pytest.raises(IntegrityError), transaction.atomic():
        AIConnection.objects.filter(pk=conn.pk).update(auth_method="oauth")
    assert not AIConnection(auth_method="personal", expires_at=None).is_expired()
    assert AIConnection(auth_method="oauth", expires_at=None).is_expired()
    assert OAuthCredential(kind=kind, expires_at=None).is_expired()


@pytest.mark.parametrize("days", ["0", "91", "", "infinite", "999999999"])
def test_personal_token_rejects_unrecognized_or_out_of_range_expiry(browser, account, days):
    response = browser.post(
        "/settings/ai-connections/tokens/",
        {
            "name": "Bad expiry",
            "days": days,
            "sites": [str(account[1].pk)],
            "scopes": ["sites:read"],
            "acknowledged": "yes",
            "notice_version": NOTICE_VERSION,
            "notice_hash": NOTICE_HASH,
        },
    )
    assert response.status_code == 400
    assert not AIConnection.objects.exists() and not OAuthClient.objects.exists()


def test_non_expiring_tokens_remain_owner_scoped(browser, account):
    conn, raw = personal(account, lifetime=None)
    other = MantecatoUser.objects.create_user(username="foreign", password="synthetic-password")
    client = Client()
    client.force_login(other)
    assert client.get("/settings/ai-connections/").context["counts"]["total"] == 0
    assert client.post(f"/settings/ai-connections/{conn.pk}/revoke/").status_code == 404
    assert verify(raw)[1].pk == conn.pk


@pytest.mark.parametrize("mutation", ["expiry", "password"])
def test_inactive_unrevoked_tokens_have_visible_revocation(browser, account, mutation):
    conn, _ = personal(account)
    if mutation == "expiry":
        AIConnection.objects.filter(pk=conn.pk).update(
            expires_at=timezone.now() - timedelta(days=1)
        )
    else:
        account[0].set_password("new-synthetic-password")
        account[0].save(update_fields=["password"])
        browser.force_login(account[0])
    response = browser.get("/settings/ai-connections/")
    assert not response.context["connections"][0]["active"]
    assert response.context["connections"][0]["revocable"]
    assert b"Revoke token" in response.content
    assert b"data-ai-access" not in response.content
    assert browser.post(f"/settings/ai-connections/{conn.pk}/revoke/").status_code == 302


def test_token_inventory_filters_counts_and_bound_cursors(browser, account):
    conn, _ = personal(account, lifetime=None)
    with transaction.atomic():
        for _ in range(11):
            create_connection(
                account[0], conn.client, "personal", [str(account[1].pk)], ["sites:read"], None
            )
        create_connection(
            account[0],
            conn.client,
            "oauth",
            [str(account[1].pk)],
            ["sites:read"],
            timedelta(days=30),
        )
    first = browser.get("/settings/ai-connections/?tab=connections&kind=personal")
    assert first.context["counts"]["personal"] == 12 and first.context["counts"]["oauth"] == 1
    assert len(first.context["connections"]) == 10
    assert all(row["personal"] for row in first.context["connections"])
    cursor = first.context["next_cursor"]
    second = browser.get(
        "/settings/ai-connections/", {"tab": "connections", "kind": "personal", "cursor": cursor}
    )
    assert len(second.context["connections"]) == 2
    assert (
        browser.get(
            "/settings/ai-connections/", {"tab": "connections", "kind": "oauth", "cursor": cursor}
        ).status_code
        == 400
    )
    connectors = browser.get("/settings/ai-connections/?tab=connections&kind=oauth")
    assert len(connectors.context["connections"]) == 1
    assert not connectors.context["connections"][0]["personal"]


def test_legacy_keys_are_already_non_expiring_listable_and_revocable(account):
    from apps.core.api_keys import validate_api_key
    from apps.settings_app.services import (
        generate_new_api_key,
        get_api_keys_for_user,
        remove_api_key,
    )

    user_id = str(account[0].pk)
    key = generate_new_api_key(user_id, "Synthetic legacy", ["read"])
    assert validate_api_key(key["key"])["userId"] == user_id
    listed = get_api_keys_for_user(user_id)
    assert len(listed) == 1 and key["key"] not in str(listed)
    assert remove_api_key(key["id"], user_id)
    assert validate_api_key(key["key"]) is None


def test_site_boundary_admin_and_no_implicit_future_sites(account):
    user, site = account
    user.role = "admin"
    user.save(update_fields=["role"])
    conn, raw = personal(account)
    other = Website.objects.create(name="Unapproved")
    assert [w["id"] for w in execute(raw, "list_sites")["websites"]] == [str(site.pk)]
    with pytest.raises(AccessDenied):
        execute(
            raw,
            "query_metrics",
            {
                "website_id": str(other.pk),
                "operation": "totals",
                "metrics": ["pageviews"],
                "range": "24h",
            },
        )
    assert AIActivity.objects.filter(outcome="permission_denied").exists()
    user.role = "user"
    user.save(update_fields=["role"])
    site.user_id = None
    site.save(update_fields=["user_id"])
    assert execute(raw, "list_sites")["websites"] == []


@pytest.mark.parametrize(
    "trust_headers,proxy_count,expected",
    [
        (False, 1, "203.0.113.10"),
        (True, 0, "203.0.113.10"),
        (True, 1, "198.51.100.7"),
    ],
)
def test_oauth_rate_key_only_uses_explicitly_configured_proxy_topology(
    settings, trust_headers, proxy_count, expected
):
    from apps.ai_connections.oauth import public_request
    from apps.ai_connections.policy import digest

    settings.TRUST_PROXY_HEADERS = trust_headers
    settings.TRUSTED_PROXY_COUNT = proxy_count
    settings.CLIENT_IP_HEADER = ""
    request = RequestFactory().get(
        "/oauth/authorize/",
        REMOTE_ADDR="203.0.113.10",
        HTTP_X_FORWARDED_FOR="192.0.2.99, 198.51.100.7",
        HTTP_CF_CONNECTING_IP="192.0.2.88",
    )
    with patch("apps.ai_connections.oauth.limit") as limiter:
        public_request(request)
    limiter.assert_called_once_with("public:" + digest(expected, "rate"), 60)


def test_oauth_rate_limit_does_not_share_bucket_between_configured_proxy_clients(settings):
    from apps.ai_connections.oauth import public_request

    settings.TRUST_PROXY_HEADERS = True
    settings.TRUSTED_PROXY_COUNT = 1
    settings.CLIENT_IP_HEADER = ""
    factory = RequestFactory()
    request = factory.get(
        "/oauth/authorize/",
        REMOTE_ADDR="203.0.113.10",
        HTTP_X_FORWARDED_FOR="192.0.2.99, 198.51.100.7",
    )
    for _ in range(60):
        public_request(request)
    with pytest.raises(AccessDenied, match="rate_limited"):
        public_request(request)
    public_request(
        factory.get(
            "/oauth/authorize/",
            REMOTE_ADDR="203.0.113.10",
            HTTP_X_FORWARDED_FOR="192.0.2.99, 198.51.100.8",
        )
    )
    with pytest.raises(AccessDenied, match="rate_limited"):
        public_request(
            factory.get(
                "/oauth/authorize/",
                REMOTE_ADDR="203.0.113.10",
                HTTP_X_FORWARDED_FOR="192.0.2.11, 198.51.100.7",
            )
        )
    assert not AIActivity.objects.exists()


@pytest.mark.parametrize("failure", ["service", "encoding"])
def test_unexpected_tool_failure_is_not_audited_as_success(account, failure):
    conn, raw = personal(account)
    behavior = (
        {"side_effect": RuntimeError("synthetic-private-error")}
        if failure == "service"
        else {"return_value": {"private": object()}}
    )
    with (
        patch("apps.ai_connections.tools.run_query", **behavior),
        pytest.raises((RuntimeError, TypeError)),
    ):
        execute(
            raw,
            "query_metrics",
            {
                "website_id": str(account[1].pk),
                "range": "24h",
                "operation": "totals",
                "metrics": ["pageviews"],
            },
        )
    row = AIActivity.objects.get()
    assert row.outcome == "unavailable"
    assert "synthetic-private-error" not in str(row.__dict__) and raw not in str(row.__dict__)
    conn.refresh_from_db()
    assert conn.verified_at is None


@pytest.mark.parametrize("search", [None, "ALPHA"])
def test_dimension_discovery_accepts_null_and_filtered_search(account, search):
    conn, raw = personal(account)
    paths = ["/synthetic-alpha", "/synthetic-beta"]
    for path in paths:
        WebsiteEvent.objects.create(
            website_id=account[1].pk,
            url_path=path,
            created_at=timezone.now() - timedelta(hours=1),
        )
    body = {
        "website_id": str(account[1].pk),
        "range": "24h",
        "dimension": "url_path",
        "search": search,
        "limit": 50,
    }
    result = execute(raw, "list_dimension_values", body)
    assert sorted(row["value"] for row in result["rows"]) == (
        paths if search is None else paths[:1]
    )
    assert body["search"] == search  # The caller's body is not mutated.
    assert AIActivity.objects.get().outcome == "success"
    conn.refresh_from_db()
    assert conn.verified_at


def test_queries_match_rest_contract_and_audit_contains_no_values(account):
    _, site = account
    conn, raw = personal(account)
    WebsiteEvent.objects.create(
        website_id=site.pk,
        url_path="/synthetic-private-path",
        created_at=timezone.now() - timedelta(hours=1),
    )
    body = {
        "website_id": str(site.pk),
        "operation": "totals",
        "metrics": ["pageviews"],
        "start": (timezone.now() - timedelta(days=1)).isoformat(),
        "end": (timezone.now() - timedelta(seconds=1)).isoformat(),
    }
    from apps.api.v1.contracts import parse_query
    from apps.api.v1.services import run_query

    assert execute(raw, "query_metrics", body) == run_query(parse_query(body))
    assert AIActivity.objects.get().action == "query_metrics"
    assert "synthetic-private-path" not in str(list(AIActivity.objects.values()))
    assert raw not in str(list(AIActivity.objects.values()))
    conn.refresh_from_db()
    assert conn.verified_at is not None


@pytest.mark.parametrize("mutation", ["password", "deleted", "expiry", "revoke", "resource"])
@pytest.mark.parametrize("lifetime", [timedelta(days=30), None], ids=["finite", "no-expiry"])
def test_credentials_fail_closed_after_account_or_grant_change(account, mutation, lifetime):
    conn, raw = personal(account, lifetime=lifetime)
    if mutation == "password":
        account[0].set_password("changed-password")
        account[0].save(update_fields=["password"])
    elif mutation == "deleted":
        account[0].deleted_at = timezone.now()
        account[0].save(update_fields=["deleted_at"])
    elif mutation == "expiry":
        conn.expires_at = timezone.now() - timedelta(seconds=1)
        conn.save(update_fields=["expires_at"])
    elif mutation == "revoke":
        revoke_owned(account[0], conn.pk)
    else:
        row = OAuthCredential.objects.get()
        row.payload["resource"] = "https://other.example.test/mcp"
        row.save(update_fields=["payload"])
    with pytest.raises(AccessDenied):
        verify(raw)


@pytest.mark.parametrize("lifetime", [timedelta(days=30), None], ids=["finite", "no-expiry"])
def test_reduction_cannot_expand_and_applies_immediately(account, lifetime):
    conn, raw = personal(account, lifetime=lifetime)
    other = Website.objects.create(user_id=account[0].pk, name="Other")
    with pytest.raises(AccessDenied):
        reduce_owned(account[0], conn.pk, [str(other.pk)], ["sites:read"])
    reduce_owned(account[0], conn.pk, [str(account[1].pk)], ["sites:read"])
    with pytest.raises(AccessDenied):
        execute(raw, "query_metrics", {})
    conn.refresh_from_db()
    assert conn.authorized_scopes == ["analytics:read", "sites:read"]
    assert AIActivity.objects.filter(outcome="permission_denied").exists()


def test_revocation_during_query_does_not_return_results(account):
    conn, raw = personal(account)

    def revoke_while_reading(spec):
        revoke_owned(account[0], conn.pk)
        return {"totals": {"pageviews": 123}}

    with (
        patch("apps.ai_connections.tools.run_query", side_effect=revoke_while_reading),
        pytest.raises(AccessDenied),
    ):
        execute(
            raw,
            "query_metrics",
            {
                "website_id": str(account[1].pk),
                "range": "24h",
                "metrics": ["pageviews"],
                "operation": "totals",
            },
        )


def test_activity_is_lazy_paginated_and_escaped(browser, account):
    conn, _ = personal(account)
    conn.client.name = '<img src=x onerror="alert(1)">'
    conn.client.save(update_fields=["name"])
    for _ in range(13):
        AIActivity.objects.create(
            connection=conn, user=account[0], action="list_sites", outcome="success"
        )
    with patch(
        "apps.ai_connections.views.paginate",
        wraps=__import__("apps.ai_connections.views", fromlist=["paginate"]).paginate,
    ) as paginate:
        response = browser.get("/settings/ai-connections/?tab=connect")
        assert not paginate.called
    response = browser.get("/settings/ai-connections/", {"tab": "activity"})
    assert len(response.context["operations"]) == 10 and response.context["next_cursor"]
    assert b"&lt;img" in response.content and b"<img src=x" not in response.content
    second = browser.get(
        "/settings/ai-connections/", {"tab": "activity", "cursor": response.context["next_cursor"]}
    )
    assert len(second.context["operations"]) == 3


@pytest.mark.parametrize("lifetime", [timedelta(days=30), None], ids=["finite", "no-expiry"])
def test_flag_off_still_allows_management_but_denies_new_tokens(
    browser, account, settings, lifetime
):
    conn, raw = personal(account, lifetime=lifetime)
    settings.AI_CONNECTIONS_ENABLED = False
    assert browser.get("/settings/ai-connections/").status_code == 200
    assert browser.post(f"/settings/ai-connections/{conn.pk}/revoke/").status_code == 302
    assert browser.post("/settings/ai-connections/tokens/", {}).status_code == 400
    with pytest.raises(AccessDenied):
        verify(raw)


def test_authenticated_reads_and_settings_have_bounded_query_counts(browser, account):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    conn, raw = personal(account)
    execute(raw, "get_connection_status")
    with CaptureQueriesContext(connection) as queries:
        verify(raw)
    assert len(queries) == 1
    with CaptureQueriesContext(connection) as queries:
        browser.get("/settings/ai-connections/?tab=connect")
    assert len(queries) <= 4
    with CaptureQueriesContext(connection) as queries:
        browser.get("/settings/ai-connections/")
    assert len(queries) <= 5
    with CaptureQueriesContext(connection) as queries:
        execute(raw, "get_connection_status")
    assert len(queries) <= 10


def test_remote_tool_input_contracts_match_independent_stdio(account):
    import asyncio

    from mantecato_mcp.server import mcp

    from apps.ai_connections.transport import create_transport

    remote, _transport = create_transport()
    independent = asyncio.run(mcp.list_tools())
    remote_tools = {tool.name: tool for tool in remote._tool_manager.list_tools()}
    for tool in independent:
        assert remote_tools[tool.name].parameters == tool.inputSchema


def test_consent_started_by_another_account_is_rejected(browser, account):
    _, _, request_id = start_flow(browser)
    other = MantecatoUser.objects.create_user(username="other", password="synthetic-password")
    browser.force_login(other)
    assert (
        browser.get("/settings/ai-connections/consent/", {"request_id": request_id}).status_code
        == 400
    )
