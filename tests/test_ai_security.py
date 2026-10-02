"""SSRF, concurrency, bounded cleanup and tenant/security negatives."""

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from io import StringIO
from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, transaction
from django.test import Client
from django.utils import timezone

from apps.ai_connections.client_metadata import PinnedBackend, fetch_metadata
from apps.ai_connections.maintenance import cleanup
from apps.ai_connections.models import AIActivity, AIConnection, OAuthClient, OAuthCredential
from apps.ai_connections.policy import (
    AccessDenied,
    create_connection,
    issue,
    resource,
    validate_redirect,
    verify,
)
from apps.ai_connections.proxy import TrustedProxyScheme
from apps.ai_connections.tools import execute
from apps.core.models import MantecatoUser, Website

pytestmark = pytest.mark.django_db


@pytest.fixture
def security_grant(settings):
    settings.DEBUG = True
    settings.AI_CONNECTIONS_ENABLED = True
    settings.MANTECATO_PUBLIC_URL = "https://analytics.example.test"
    from apps.ai_connections.policy import _rate

    _rate.clear()
    user = MantecatoUser.objects.create_user(
        username="security-owner", password="synthetic-password"
    )
    site = Website.objects.create(user_id=user.pk, name="Example")
    with transaction.atomic():
        client = OAuthClient.objects.create(
            client_id="security-client",
            name="Test",
            redirect_uris=["https://client.example.test/callback"],
        )
        conn = create_connection(
            user,
            client,
            "oauth",
            [str(site.pk)],
            ["sites:read", "analytics:read"],
            timedelta(days=30),
        )
        raw = issue(
            "access", {"resource": resource(), "scopes": conn.scopes}, timedelta(minutes=15), conn
        )
    return user, site, conn, raw


@pytest.mark.parametrize(
    "uri",
    [
        "https://*.example.test/callback",
        "javascript:alert(1)",
        "http://client.example.test/callback",
        "https://user:password@client.example.test/callback",
        "https://client.example.test/#fragment",
        "https://127.0.0.1/callback",
        "https://169.254.169.254/callback",
        "https://localhost./callback",
        "https://client.example.test/callback?code=x",
    ],
)
def test_bad_redirects(uri):
    with pytest.raises(AccessDenied):
        validate_redirect(uri)


@pytest.mark.parametrize("parameter", ["code", "state", "iss", "error"])
@pytest.mark.parametrize(
    "query", ["{parameter}", "{parameter}=", "locale=en&{parameter}=", "{parameter}=&{parameter}=x"]
)
def test_reserved_redirect_parameters_are_rejected_even_when_empty(parameter, query):
    uri = "https://client.example.test/callback?" + query.format(parameter=parameter)
    with pytest.raises(AccessDenied, match="invalid_redirect_uri"):
        validate_redirect(uri)


def test_encoded_reserved_redirect_parameter_is_rejected_when_empty():
    with pytest.raises(AccessDenied, match="invalid_redirect_uri"):
        validate_redirect("https://client.example.test/callback?co%64e=")


def test_registration_rejects_empty_reserved_redirect_parameter(security_grant):
    response = Client().post(
        "/oauth/register/",
        data=json.dumps(
            {
                "client_name": "Synthetic callback client",
                "redirect_uris": ["https://client.example.test/callback?code="],
                "token_endpoint_auth_method": "none",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_redirect_uri"
    assert not OAuthClient.objects.filter(name="Synthetic callback client").exists()


@pytest.mark.parametrize(
    "uri",
    [
        "https://client.example.test/callback",
        "https://client.example.test/callback?locale=&return_to",
        "http://127.0.0.1:54321/callback",
        "http://[::1]:54321/callback",
    ],
)
def test_valid_redirects(uri):
    assert validate_redirect(uri) == uri


@pytest.mark.parametrize(
    "allowed,peer",
    [
        ("127.0.0.1", "127.0.0.1"),
        ("192.0.2.0/24", "192.0.2.10"),
        ("::1", "::1"),
        ("*", "192.0.2.10"),
    ],
)
def test_proxy_scheme_trusts_only_explicit_peers_without_rewriting_identity(allowed, peer):
    scope = {
        "type": "http",
        "scheme": "http",
        "client": (peer, 1234),
        "headers": [(b"x-forwarded-proto", b"https"), (b"x-forwarded-for", b"203.0.113.1")],
    }
    adapted = TrustedProxyScheme(allowed)(scope)
    assert adapted == {**scope, "scheme": "https"}
    assert scope["scheme"] == "http"
    assert adapted["client"] == scope["client"]


@pytest.mark.parametrize(
    "values",
    [[], [b"http"], [b"https,http"], [b"https", b"http"], [b"https", b"https"], [b"HTTPS"]],
)
def test_proxy_scheme_rejects_ambiguous_or_missing_proto(values):
    scope = {
        "type": "http",
        "scheme": "http",
        "client": ("127.0.0.1", 1234),
        "headers": [(b"x-forwarded-proto", value) for value in values],
    }
    assert TrustedProxyScheme("127.0.0.1")(scope) is scope


@pytest.mark.parametrize("allowed", ["", "192.0.2.10", "not-an-address", "*,invalid"])
def test_proxy_scheme_fails_closed_for_untrusted_or_invalid_configuration(allowed):
    scope = {
        "type": "http",
        "scheme": "http",
        "client": ("127.0.0.1", 1234),
        "headers": [(b"x-forwarded-proto", b"https")],
    }
    assert TrustedProxyScheme(allowed)(scope) is scope


def test_proxy_scheme_preserves_direct_tls_and_requires_an_ip_peer():
    adapter = TrustedProxyScheme("*")
    scope = {"type": "http", "scheme": "https", "client": ("127.0.0.1", 1234)}
    assert adapter(scope) is scope
    scope = {"type": "http", "scheme": "http", "headers": [(b"x-forwarded-proto", b"https")]}
    assert adapter(scope) is scope


@pytest.mark.parametrize(
    "addresses",
    [
        ["127.0.0.1"],
        ["10.0.0.1"],
        ["169.254.169.254"],
        ["::1"],
        ["fe80::1"],
        ["8.8.8.8", "192.168.1.1"],
    ],
)
def test_metadata_blocks_all_private_dns_results_before_connect(addresses):
    with (
        patch("apps.ai_connections.client_metadata.public_addresses", return_value=addresses),
        patch("apps.ai_connections.client_metadata.httpcore.ConnectionPool") as pool,
        pytest.raises(AccessDenied),
    ):
        fetch_metadata("https://client.example.test/metadata.json")
    pool.assert_not_called()


def test_backend_pins_dns_address_and_retains_pool_hostname():
    backend = PinnedBackend("client.example.test", 443, ["8.8.8.8"])
    backend.backend = Mock()
    backend.connect_tcp("client.example.test", 443, timeout=3)
    assert backend.backend.connect_tcp.call_args.args[:2] == ("8.8.8.8", 443)
    with pytest.raises(AccessDenied):
        backend.connect_tcp("attacker.example.test", 443)


@pytest.mark.parametrize(
    "status,body", [(302, b"{}"), (200, b"x" * 16385), (200, b'{"client_id":"x","client_id":"y"}')]
)
def test_metadata_rejects_redirects_oversize_duplicate_keys(status, body):
    response = Mock(status=status, headers=[(b"content-type", b"application/json")])
    response.iter_stream.return_value = iter([body])

    @contextmanager
    def stream(*args, **kwargs):
        yield response

    pool = Mock()
    pool.stream.side_effect = stream

    @contextmanager
    def open_pool(*args, **kwargs):
        yield pool

    with (
        patch("apps.ai_connections.client_metadata.public_addresses", return_value=["8.8.8.8"]),
        patch("apps.ai_connections.client_metadata.httpcore.ConnectionPool", side_effect=open_pool),
        pytest.raises(AccessDenied),
    ):
        fetch_metadata("https://client.example.test/metadata.json")


def test_metadata_valid_document_is_pinned_and_not_redirected():
    url = "https://client.example.test/metadata.json"
    response = Mock(status=200, headers=[(b"content-type", b"application/json; charset=utf-8")])
    response.iter_stream.return_value = iter(
        [
            json.dumps(
                {
                    "client_id": url,
                    "client_name": "Test",
                    "redirect_uris": ["https://client.example.test/callback"],
                }
            ).encode()
        ]
    )

    @contextmanager
    def stream(method, target, **kwargs):
        assert target == url  # Original hostname remains the TLS/SNI identity.
        yield response

    pool = Mock()
    pool.stream.side_effect = stream

    @contextmanager
    def open_pool(**kwargs):
        assert kwargs["network_backend"].addresses == ["8.8.8.8"] and kwargs["retries"] == 0
        yield pool

    with (
        patch("apps.ai_connections.client_metadata.public_addresses", return_value=["8.8.8.8"]),
        patch("apps.ai_connections.client_metadata.httpcore.ConnectionPool", side_effect=open_pool),
    ):
        assert fetch_metadata(url) == ("Test", ["https://client.example.test/callback"])


@pytest.mark.django_db(transaction=True)
def test_atomic_refresh_replay_revokes_family(security_grant):
    _, _, conn, _ = security_grant
    old = issue(
        "refresh", {"resource": resource(), "scopes": conn.scopes}, timedelta(days=30), conn
    )

    def refresh():
        close_old_connections()
        try:
            result = Client().post(
                "/oauth/token/",
                {
                    "grant_type": "refresh_token",
                    "client_id": conn.client_id,
                    "refresh_token": old,
                    "resource": resource(),
                },
            )
            return result.status_code, result.json()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: refresh(), range(2)))
    assert sorted(status for status, _ in responses) == [200, 400]
    conn.refresh_from_db()
    assert conn.revoked_at
    new = next(body["access_token"] for status, body in responses if status == 200)
    with pytest.raises(AccessDenied):
        verify(new)


def test_response_budget_and_scope_denials_are_metadata_only(security_grant, settings):
    _, site, conn, raw = security_grant
    settings.AI_MAX_RESPONSE_BYTES = 10
    with pytest.raises(AccessDenied, match="result_too_large"):
        execute(
            raw,
            "query_metrics",
            {"website_id": str(site.pk), "metrics": ["pageviews"], "range": "24h"},
        )
    assert AIActivity.objects.get().outcome == "result_too_large"
    conn.refresh_from_db()
    assert not conn.verified_at


def test_foreign_management_is_not_accessible(security_grant):
    _, _, conn, _ = security_grant
    other = MantecatoUser.objects.create_user(username="foreign", password="synthetic-password")
    client = Client()
    client.force_login(other)
    assert client.post(f"/settings/ai-connections/{conn.pk}/revoke/").status_code == 404
    assert client.post(f"/settings/ai-connections/{conn.pk}/reduce/").status_code == 404
    conn.refresh_from_db()
    assert not conn.revoked_at


def test_cleanup_retention_batches_idempotence_and_valid_token_protection(security_grant):
    user, _, conn, raw = security_grant
    old = timezone.now() - timedelta(days=91)
    for _ in range(5):
        row = AIActivity.objects.create(
            connection=conn, user=user, action="list_sites", outcome="success"
        )
        AIActivity.objects.filter(pk=row.pk).update(created_at=old)
    AIActivity.objects.create(connection=conn, user=user, action="list_sites", outcome="success")
    for _ in range(5):
        issue("request", {}, timedelta(seconds=-1))
    before = cleanup(dry_run=True, batch_size=2)
    assert before["deleted"]["credentials"] == 5 and OAuthCredential.objects.count() == 6
    result = cleanup(batch_size=2)
    assert result["deleted"]["credentials"] == 5 and result["deleted"]["activity"] == 5
    verify(raw)
    assert AIActivity.objects.count() == 1
    assert not any(cleanup(batch_size=2)["deleted"].values())


def test_cleanup_soft_deleted_owner(security_grant):
    user, _, _, _ = security_grant
    user.deleted_at = timezone.now()
    user.save(update_fields=["deleted_at"])
    assert cleanup(batch_size=1)["deleted"]["connections"] == 1
    assert not OAuthCredential.objects.exists() and not AIConnection.objects.exists()


@pytest.mark.parametrize("status", ["busy", "error"])
def test_cleanup_attempted_independently_of_rollup(status):
    path = "apps.core.management.commands.run_daily_maintenance"
    behavior = (
        {"return_value": {"status": status}}
        if status == "busy"
        else {"side_effect": RuntimeError("not logged")}
    )
    with (
        patch(path + ".rollup_finished_periods", **behavior),
        patch(path + ".cleanup", return_value={"status": "completed"}) as ai,
        pytest.raises(CommandError),
    ):
        call_command("run_daily_maintenance", stdout=StringIO())
    ai.assert_called_once()


def test_real_pinned_tls_metadata_fetch_retains_sni(tmp_path):
    import ssl
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    import httpcore
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    host = "client.example.test"
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(timezone.now() - timedelta(hours=1))
        .not_valid_after(timezone.now() + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.headers["Host"] == f"{host}:{self.server.server_port}"
            body = json.dumps(
                {
                    "client_id": url,
                    "client_name": "Test TLS",
                    "redirect_uris": ["https://client.example.test/callback"],
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    url = f"https://{host}:{server.server_port}/metadata.json"
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(cert_path, key_path)
    sni = []
    tls.set_servername_callback(lambda sock, name, context: sni.append(name))
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    trusted = ssl.create_default_context(cafile=str(cert_path))
    real_pool, real_connect = httpcore.ConnectionPool, httpcore.SyncBackend.connect_tcp

    def pinned_local(self, address, port, *args, **kwargs):
        assert address == "8.8.8.8"  # Only the test maps this public address to loopback.
        return real_connect(self, "127.0.0.1", port, *args, **kwargs)

    try:
        with (
            patch("apps.ai_connections.client_metadata.public_addresses", return_value=["8.8.8.8"]),
            patch(
                "apps.ai_connections.client_metadata.httpcore.ConnectionPool",
                side_effect=lambda **kw: real_pool(ssl_context=trusted, **kw),
            ),
            patch.object(httpcore.SyncBackend, "connect_tcp", pinned_local),
        ):
            assert fetch_metadata(url) == ("Test TLS", ["https://client.example.test/callback"])
        assert sni == [host]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.django_db(transaction=True)
def test_concurrent_code_consumption_is_one_time(security_grant):
    from authlib.oauth2.rfc7636 import create_s256_code_challenge

    _, _, conn, _ = security_grant
    verifier = "v" * 64
    code = issue(
        "code",
        {
            "resource": resource(),
            "scopes": conn.scopes,
            "redirect_uri": "https://client.example.test/callback",
            "code_challenge": create_s256_code_challenge(verifier),
        },
        timedelta(minutes=5),
        conn,
    )

    def exchange():
        close_old_connections()
        try:
            return (
                Client()
                .post(
                    "/oauth/token/",
                    {
                        "grant_type": "authorization_code",
                        "client_id": conn.client_id,
                        "code": code,
                        "code_verifier": verifier,
                        "redirect_uri": "https://client.example.test/callback",
                        "resource": resource(),
                    },
                )
                .status_code
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: exchange(), range(2))) == [200, 400]
    conn.refresh_from_db()
    assert conn.revoked_at


@pytest.mark.django_db(transaction=True)
def test_reduction_during_query_does_not_disclose_results(security_grant):
    import threading

    from apps.ai_connections.policy import reduce_owned

    user, site, conn, raw = security_grant
    reading, resume = threading.Event(), threading.Event()

    def slow(spec):
        reading.set()
        assert resume.wait(timeout=5)
        return {"totals": {"pageviews": 123}}

    def read():
        close_old_connections()
        try:
            with pytest.raises(AccessDenied):
                execute(
                    raw, "query_metrics", {"website_id": str(site.pk), "metrics": ["pageviews"]}
                )
        finally:
            close_old_connections()

    with (
        patch("apps.ai_connections.tools.run_query", side_effect=slow),
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        future = pool.submit(read)
        assert reading.wait(timeout=5)
        reduce_owned(user, conn.pk, [str(site.pk)], ["sites:read"])
        resume.set()
        future.result(timeout=5)
