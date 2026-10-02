"""Real official SDK/OAuth clients against two native Gunicorn ASGI workers."""

import asyncio
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit

import httpx
import pytest
from django.db import connection
from django.test import Client
from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientMetadata

from apps.ai_connections.policy import NOTICE_HASH, NOTICE_VERSION
from apps.core.models import MantecatoUser, Website

pytestmark = pytest.mark.django_db(transaction=True)


class MemoryStorage:
    tokens = None
    client = None

    async def get_tokens(self):
        return self.tokens

    async def set_tokens(self, tokens):
        self.tokens = tokens

    async def get_client_info(self):
        return self.client

    async def set_client_info(self, client):
        self.client = client


def integration_database_url(config, env):
    """Skip unsupported setups before writing fixtures or launching a worker."""
    host = config.get("OPTIONS", {}).get("host") or config.get("HOST")
    if not host or not host.startswith("/"):
        pytest.skip("HTTP integration requires isolated socket PostgreSQL")
    name = config["NAME"]
    if not (name.startswith("test_") or name.endswith("_test")):
        pytest.skip("HTTP integration requires a test database")
    database_url = env.get("TEST_DATABASE_URL") or env.get("DATABASE_URL")
    if not database_url:
        pytest.skip("HTTP integration requires a database URL")
    parsed = urlsplit(database_url)
    if (
        parsed.scheme not in ("postgres", "postgresql")
        or parsed.hostname
        or parse_qs(parsed.query).get("host") != [host]
    ):
        pytest.skip("HTTP integration URL must match the isolated PostgreSQL socket")
    return urlunsplit(parsed._replace(path="/" + name))


@pytest.mark.parametrize("key", ["TEST_DATABASE_URL", "DATABASE_URL"])
def test_http_fixture_database_url_selection(key):
    config = {"NAME": "test_synthetic", "OPTIONS": {"host": "/tmp/synthetic-pg"}}
    env = {key: "postgresql://postgres@/synthetic?host=/tmp/synthetic-pg"}
    if key == "TEST_DATABASE_URL":
        env["DATABASE_URL"] = "postgresql://postgres@db.example.test/other"
    assert integration_database_url(config, env) == (
        "postgresql://postgres@/test_synthetic?host=/tmp/synthetic-pg"
    )


@pytest.mark.parametrize(
    "name,host,url",
    [
        ("test_synthetic", "127.0.0.1", "postgresql://postgres@127.0.0.1/test_synthetic"),
        ("not_a_fixture", "/tmp/synthetic-pg", ""),
        ("test_synthetic", "/tmp/synthetic-pg", ""),
        (
            "test_synthetic",
            "/tmp/synthetic-pg",
            "postgresql://postgres@db.example.test/test_synthetic",
        ),
        ("test_synthetic", "/tmp/synthetic-pg", "postgresql://postgres@/base?host=/tmp/other-pg"),
    ],
)
def test_http_fixture_skips_unsupported_database_settings(name, host, url):
    with pytest.raises(pytest.skip.Exception):
        integration_database_url({"NAME": name, "HOST": host}, {"DATABASE_URL": url})


@pytest.fixture
def http_server(tmp_path, request):
    env = dict(os.environ)
    database_url = integration_database_url(connection.settings_dict, env)
    user = MantecatoUser.objects.create_user(username="sdk-owner", password="synthetic-password")
    site = Website.objects.create(user_id=user.pk, name="Synthetic", domain="https://example.test")
    browser = Client()
    browser.force_login(user)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    env.update(
        DATABASE_URL=database_url,
        TEST_DATABASE_URL=database_url,
        DEBUG="True",
        MANTECATO_PUBLIC_URL=origin,
        SECURE_SSL_REDIRECT="False",
        ALLOWED_HOSTS="127.0.0.1",
        CONN_MAX_AGE="0",
        FORWARDED_ALLOW_IPS="127.0.0.1,::1",
    )
    env.update(getattr(request, "param", {}))
    log = (tmp_path / "http.log").open("w+")
    subprocess.run(
        [sys.executable, "manage.py", "collectstatic", "--noinput"],
        env=env,
        stdout=log,
        stderr=log,
        check=True,
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "gunicorn",
            "mantecato.asgi:application",
            "--worker-class",
            "asgi",
            "--workers",
            "2",
            "--worker-connections",
            "16",
            "--graceful-timeout",
            "2",
            "--keep-alive",
            "0",
            "--bind",
            f"127.0.0.1:{port}",
            "--access-logfile",
            "-",
            "--access-logformat",
            "%(m)s %(s)s %(D)s",
        ],
        env=env,
        stdout=log,
        stderr=log,
    )
    try:
        for _ in range(100):
            if process.poll() is not None:
                log.seek(0)
                pytest.fail(log.read())
            try:
                if httpx.get(origin + "/health/", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.05)
        else:
            pytest.fail("ASGI startup did not complete")
        yield origin, browser.cookies["sessionid"].value, str(site.pk), log
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        log.close()


PROXY_ENV = {
    "DEBUG": "False",
    "MANTECATO_PUBLIC_URL": "https://analytics.example.test",
    "ALLOWED_HOSTS": "127.0.0.1,analytics.example.test",
    "USE_SECURE_PROXY_SSL_HEADER": "False",
}


@pytest.mark.parametrize(
    "http_server,forwarded_proto,expected_status",
    [
        ({**PROXY_ENV, "FORWARDED_ALLOW_IPS": "127.0.0.1"}, "https", 401),
        ({**PROXY_ENV, "FORWARDED_ALLOW_IPS": "192.0.2.10"}, "https", 404),
        ({**PROXY_ENV, "FORWARDED_ALLOW_IPS": "127.0.0.1"}, None, 404),
    ],
    indirect=["http_server"],
    ids=["trusted-tls-proxy", "untrusted-forwarded-header", "missing-forwarded-header"],
)
def test_production_mcp_requires_https_from_trusted_proxy(
    http_server, forwarded_proto, expected_status
):
    origin, _, _, _ = http_server
    headers = {"Host": "analytics.example.test"}
    if forwarded_proto:
        headers["X-Forwarded-Proto"] = forwarded_proto
    response = httpx.post(origin + "/mcp", headers=headers, timeout=10)
    assert response.status_code == expected_status
    if expected_status == 401:
        assert (
            "https://analytics.example.test/.well-known/oauth-protected-resource/mcp"
            in (response.headers["www-authenticate"])
        )
    else:
        assert response.json()["error"] == "ai_access_unavailable"


@pytest.mark.parametrize(
    "http_server",
    [
        {"MANTECATO_PUBLIC_URL": ""},
        {"MANTECATO_PUBLIC_URL": "https://analytics.example.test/path"},
    ],
    indirect=True,
    ids=["no-public-url", "invalid-public-url"],
)
def test_unconfigured_ai_keeps_web_runtime_healthy_without_new_grants(http_server):
    origin, cookie, _, _ = http_server
    with httpx.Client(base_url=origin, timeout=10) as client:
        assert client.get("/health/").status_code == 200
        assert client.get("/login/").status_code == 200
        assert client.get("/api/script").status_code == 200
        assert client.options("/api/send").status_code == 204
        response = client.post("/mcp")
        assert response.status_code == 404
        assert response.json()["error"] == "ai_access_unavailable"
        assert response.headers["cache-control"] == "no-store"
        for path in (
            "/.well-known/oauth-authorization-server",
            "/.well-known/oauth-protected-resource/mcp",
        ):
            response = client.get(path)
            assert response.status_code == 404
            assert response.json()["error"] == "public_endpoint_required"
        for path in ("/oauth/register/", "/oauth/token/"):
            response = client.post(path)
            assert response.status_code == 400
            assert response.json()["error"] == "public_endpoint_required"
        client.cookies.set("sessionid", cookie)
        response = client.get("/settings/ai-connections/")
        assert response.status_code == 200
        assert "MANTECATO_PUBLIC_URL" in response.text
        assert "<fieldset disabled>" in response.text
        response = client.post("/settings/ai-connections/tokens/", follow_redirects=False)
        assert response.status_code == 403  # Missing CSRF remains rejected even unconfigured.


def test_sdk_oauth_discovery_pkce_tools_and_legacy_smoke(http_server):
    origin, cookie, site_id, log = http_server

    async def scenario():
        storage = MemoryStorage()
        callback = None
        async with httpx.AsyncClient(
            cookies={"sessionid": cookie}, follow_redirects=False, timeout=15
        ) as browser:

            async def redirect(url):
                nonlocal callback
                response = await browser.get(url)
                assert response.status_code == 302, response.text
                location = response.headers["location"]
                request_id = parse_qs(urlsplit(location).query)["request_id"][0]
                consent = await browser.get(origin + location)
                assert consent.status_code == 200
                response = await browser.post(
                    origin + "/settings/ai-connections/consent/",
                    data={
                        "csrfmiddlewaretoken": browser.cookies["csrftoken"],
                        "request_id": request_id,
                        "approve": "yes",
                        "acknowledged": "yes",
                        "sites": site_id,
                        "scopes": "analytics:read",
                        "notice_hash": NOTICE_HASH,
                        "notice_version": NOTICE_VERSION,
                    },
                )
                assert response.status_code == 302, response.text
                query = parse_qs(urlsplit(response.headers["location"]).query)
                callback = query["code"][0], query["state"][0]

            async def receive_callback():
                return callback

            auth = OAuthClientProvider(
                server_url=origin + "/mcp",
                client_metadata=OAuthClientMetadata(
                    client_name="Synthetic SDK",
                    redirect_uris=["http://127.0.0.1:54321/callback"],
                    scope="analytics:read sites:read",
                    token_endpoint_auth_method="none",
                ),
                storage=storage,
                redirect_handler=redirect,
                callback_handler=receive_callback,
            )
            async with (
                httpx.AsyncClient(auth=auth, timeout=15) as client,
                streamable_http_client(origin + "/mcp", http_client=client) as (read, write, _),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                tools = await session.list_tools()
                assert len(tools.tools) == 8
                assert all(tool.annotations.readOnlyHint for tool in tools.tools)
                status = await session.call_tool("get_connection_status", {})
                assert not status.isError
                stats = await session.call_tool(
                    "query_metrics",
                    {"website_id": site_id, "metrics": ["pageviews"], "range": "24h"},
                )
                assert not stats.isError
                for search in (None, "synthetic"):
                    values = await session.call_tool(
                        "list_dimension_values",
                        {"website_id": site_id, "dimension": "url_path", "search": search},
                    )
                    assert not values.isError
                denied = await session.call_tool("list_sites", {})
                assert denied.isError  # User reduced the advertised scope at consent.
            assert storage.tokens and storage.tokens.refresh_token
            for _ in range(5):
                async with (
                    httpx.AsyncClient(
                        headers={"Authorization": "Bearer " + storage.tokens.access_token},
                        timeout=15,
                    ) as client,
                    streamable_http_client(origin + "/mcp", http_client=client) as (read, write, _),
                    ClientSession(read, write) as session,
                ):
                    await session.initialize()
                    assert not (await session.call_tool("get_connection_status", {})).isError
            script_response = await browser.get(origin + "/api/script")
            assert script_response.status_code == 200
            assert script_response.headers["connection"] == "close"
            assert (
                await browser.options(
                    origin + "/api/send",
                    headers={
                        "Origin": "https://example.test",
                        "Access-Control-Request-Method": "POST",
                    },
                )
            ).status_code == 204
            assert (await browser.get(origin + "/login/")).status_code in (200, 302)
            assert (
                await browser.get(origin + "/mcp")
            ).status_code == 401  # Cookies never authenticate MCP.
            response = await browser.post(
                origin + "/mcp",
                headers={
                    "Authorization": "Bearer " + storage.tokens.access_token,
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                    "Origin": "https://attacker.example.test",
                },
                content='{"jsonrpc":"2.0","id":1,"method":"tools/list"}',
            )
            assert response.status_code == 403
            log.flush()
            log.seek(0)
            output = log.read()
            assert storage.tokens.access_token not in output and callback[0] not in output

    asyncio.run(scenario())


@pytest.mark.parametrize("expiry", ["30", "never"])
def test_real_browser_token_history_mobile_and_lazy_activity(http_server, expiry):
    playwright = pytest.importorskip("playwright.sync_api")
    origin, cookie, _, _ = http_server
    with playwright.sync_playwright() as pw:
        chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        options = {"headless": True}
        if chrome.exists():
            options["executable_path"] = str(chrome)
        try:
            browser = pw.chromium.launch(**options)
        except playwright.Error:
            pytest.skip("Install a Playwright Chromium browser to run UI checks")
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 1000})
            context.add_cookies(
                [
                    {
                        "name": "sessionid",
                        "value": cookie,
                        "url": origin,
                        "httpOnly": True,
                        "sameSite": "Lax",
                    }
                ]
            )
            context.add_init_script(
                "Object.defineProperty(navigator, 'clipboard', "
                "{value: undefined, configurable: true})"
            )
            page = context.new_page()
            response = page.goto(origin + "/settings/ai-connections/")
            assert response.status == 200
            page.wait_for_selector("[data-ai-enhanced]")
            assert page.locator("[data-ai-guide]:visible").count() == 1
            page.wait_for_function(
                "(() => { const images = Array.from(document.querySelectorAll('.ai-provider img'));"
                "return images.length === 5 && "
                "images.every(i => i.complete && i.naturalWidth > 0); })()"
            )
            page.locator("[data-ai-provider=grok]").click()
            page.get_by_role("heading", name="Connect Grok", exact=True).wait_for()
            page.locator("[data-ai-provider=grok]").press("ArrowLeft")
            page.get_by_role("heading", name="Connect Gemini", exact=True).wait_for()
            assert page.locator("[data-ai-guide]:visible").count() == 1
            page.set_viewport_size({"width": 320, "height": 740})
            assert page.locator("#ai-content").evaluate("e => e.scrollWidth <= e.clientWidth + 1")
            page.set_viewport_size({"width": 1280, "height": 1000})
            page.get_by_text("Create a personal token", exact=True).click()
            page.locator("input[name=name]").fill("Synthetic desktop")
            page.locator("#ai-days").select_option(expiry)
            page.locator("input[name=sites]").first.check()
            page.locator("input[name=acknowledged]").check()
            with page.expect_navigation() as navigation:
                page.get_by_role("button", name="Create read-only token").click()
            assert navigation.value.headers["cache-control"] == "no-store"
            assert navigation.value.status == 200, page.locator("body").inner_text()
            token = page.locator("#ai-new-token").input_value()
            assert token.startswith("mai_")
            page.get_by_role("button", name="Copy token", exact=True).click()
            page.wait_for_function(
                "document.querySelector('[data-ai-copy-status]').textContent.includes('manually')"
            )
            assert page.locator("#ai-new-token").evaluate("e => e.selectionEnd") == len(token)
            assert page.get_by_role("heading", name="Your connections & tokens").is_visible()
            if expiry == "never":
                assert "Never expires" in page.locator(".ai-connection").inner_text()
            assert page.locator("[data-ai-revoke] > summary").is_visible()
            assert page.locator("[data-ai-revoke]").evaluate("e => !e.closest('[data-ai-access]')")
            page.get_by_role("link", name="Connections & tokens", exact=True).click()
            page.wait_for_selector("#ai-new-token", state="detached")
            page.wait_for_selector("[data-ai-access]")
            assert token not in page.content()
            page.screenshot(
                path=f"/tmp/mantecato-ai-tokens-desktop-{expiry}.png",
                full_page=True,
                animations="disabled",
            )
            page.set_viewport_size({"width": 320, "height": 740})
            assert page.locator("#ai-content").evaluate("e => e.scrollWidth <= e.clientWidth + 1")
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(350)
            assert page.locator("#ai-content").evaluate("e => e.scrollWidth <= e.clientWidth + 1")
            assert page.locator("#ai-content").bounding_box()["x"] >= 0
            page.screenshot(
                path=f"/tmp/mantecato-ai-tokens-mobile-{expiry}.png",
                full_page=True,
                animations="disabled",
            )
            page.get_by_role("link", name="Add connector", exact=True).click()
            page.wait_for_selector("[data-ai-enhanced]")
            page.locator("[data-ai-provider=chatgpt]").click()
            page.get_by_role("heading", name="Connect ChatGPT", exact=True).wait_for()
            assert page.locator("[data-ai-guide]:visible").count() == 1
            page.get_by_role("link", name="Activity", exact=True).click()
            page.get_by_text("Created personal token", exact=True).wait_for()
            assert token not in page.evaluate("JSON.stringify(localStorage)")
            assert token not in page.evaluate("JSON.stringify(sessionStorage)")
            page.screenshot(
                path="/tmp/mantecato-ai-mobile.png", full_page=True, animations="disabled"
            )
            page.get_by_role("link", name="Connections & tokens", exact=True).click()
            page.wait_for_selector("[data-ai-revoke]")
            page.locator("[data-ai-revoke] > summary").press("Enter")
            with page.expect_navigation():
                page.get_by_role("button", name="Confirm revocation", exact=True).click()
            page.get_by_text("Revoked", exact=True).wait_for()
            assert page.locator("[data-ai-revoke]").count() == 0
            assert (
                httpx.post(
                    origin + "/mcp", headers={"Authorization": "Bearer " + token}, timeout=10
                ).status_code
                == 401
            )
        finally:
            browser.close()


def test_no_expiry_personal_token_authenticates_official_sdk_and_can_be_revoked(http_server):
    from apps.ai_connections.models import AIConnection, OAuthCredential

    origin, cookie, site_id, _ = http_server
    with httpx.Client(cookies={"sessionid": cookie}, timeout=15) as browser:
        assert browser.get(origin + "/settings/ai-connections/").status_code == 200
        response = browser.post(
            origin + "/settings/ai-connections/tokens/",
            data={
                "csrfmiddlewaretoken": browser.cookies["csrftoken"],
                "name": "No expiry SDK",
                "days": "never",
                "sites": site_id,
                "scopes": "analytics:read",
                "acknowledged": "yes",
                "notice_hash": NOTICE_HASH,
                "notice_version": NOTICE_VERSION,
            },
        )
        assert response.status_code == 200
        raw = re.search(r'id="ai-new-token"[^>]*value="([^"]+)"', response.text).group(1)
        conn = AIConnection.objects.get(client__name="No expiry SDK")
        assert conn.expires_at is None
        assert OAuthCredential.objects.get(connection=conn).expires_at is None

        async def scenario():
            async with (
                httpx.AsyncClient(headers={"Authorization": "Bearer " + raw}, timeout=15) as client,
                streamable_http_client(origin + "/mcp", http_client=client) as (read, write, _),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                assert len((await session.list_tools()).tools) == 8
                result = await session.call_tool("get_connection_status", {})
                assert not result.isError
                assert json.loads(result.content[0].text)["expires_at"] is None

        asyncio.run(scenario())
        assert (
            browser.post(
                origin + f"/settings/ai-connections/{conn.pk}/revoke/",
                data={"csrfmiddlewaretoken": browser.cookies["csrftoken"]},
            ).status_code
            == 302
        )
        assert (
            browser.post(origin + "/mcp", headers={"Authorization": "Bearer " + raw}).status_code
            == 401
        )
        assert not OAuthCredential.objects.filter(connection=conn).exists()


def test_concurrent_http_closes_database_connections(http_server):
    origin, _, _, _ = http_server

    async def burst():
        async with httpx.AsyncClient(limits=httpx.Limits(max_connections=8), timeout=10) as client:
            responses = await asyncio.gather(*(client.get(origin + "/health/") for _ in range(120)))
            assert all(response.status_code == 200 for response in responses)
            assert all(response.headers["connection"] == "close" for response in responses)

    asyncio.run(burst())
    time.sleep(0.3)
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
        assert cursor.fetchone()[0] == 1  # Test observer only, no web ORM sockets.
