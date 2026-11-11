"""Admission is bounded before ORM threads and never queues collector traffic."""

import asyncio
import os
import subprocess
import sys
from unittest.mock import patch

import pytest

from mantecato.admission import AnalyticsGate, is_analytics, unavailable


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/pages/",
        "/overview/tab/",
        "/api/v1/query/",
        "/api/analytics/overview/",
        "/dashboards/x/widget/y/",
        "/mcp",
    ],
)
def test_analytics_routes_share_budget(path):
    assert is_analytics({"type": "http", "method": "GET", "path": path})


@pytest.mark.parametrize(
    "path",
    [
        "/api/send",
        "/api/script",
        "/health/",
        "/login/",
        "/oauth/token/",
        "/static/css/theme.css",
        "/pages-not-real/",
    ],
)
def test_collection_and_control_routes_bypass_budget(path):
    assert not is_analytics({"type": "http", "method": "POST", "path": path})
    assert not is_analytics({"type": "http", "method": "OPTIONS", "path": "/mcp"})
    assert not is_analytics({"type": "lifespan"})


def test_queue_bound_cancellation_and_slot_cleanup():
    async def run():
        gate = AnalyticsGate(1, 1, 1)
        started = asyncio.Event()

        async def waiting():
            started.set()
            async with gate.slot() as admitted:
                assert admitted

        async with gate.slot() as admitted:
            assert admitted
            task = asyncio.create_task(waiting())
            await started.wait()
            assert gate.waiting == 1
            async with gate.slot() as rejected:
                assert not rejected
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert gate.waiting == 0
        assert gate.running == 0

        # Cancellation of active work must release the slot as well.
        async def active():
            async with gate.slot():
                await asyncio.Event().wait()

        task = asyncio.create_task(active())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert gate.running == 0

    asyncio.run(run())


def test_waiter_timeout_and_successful_wakeup():
    async def run():
        gate = AnalyticsGate(1, 1, 0.01)
        async with gate.slot():
            async with gate.slot() as admitted:
                assert not admitted
            assert gate.waiting == 0

        async def waiting():
            async with gate.slot() as admitted:
                assert admitted

        async with gate.slot():
            task = asyncio.create_task(waiting())
            await asyncio.sleep(0)
        await task
        assert gate.running == 0 and gate.waiting == 0

    asyncio.run(run())


def test_asgi_saturation_returns_retry_without_entering_django_and_preserves_collector(settings):
    settings.MANTECATO_PUBLIC_URL = ""
    settings.ANALYTICS_MAX_CONCURRENT = 1
    settings.ANALYTICS_MAX_WAITING = 0
    from mantecato.asgi import create_application

    async def run():
        active = asyncio.Event()
        release = asyncio.Event()
        calls = []

        async def django(scope, receive, send):
            calls.append(scope["path"])
            if scope["path"] == "/pages/":
                active.set()
                await release.wait()

        with patch("mantecato.asgi.get_asgi_application", return_value=django):
            app = create_application()
        page = {"type": "http", "path": "/pages/", "method": "GET"}
        messages = []

        async def send(message):
            messages.append(message)

        task = asyncio.create_task(app(page, None, send))
        await active.wait()
        await app({**page, "path": "/sections/"}, None, send)
        assert messages[0]["status"] == 503
        assert (b"retry-after", b"1") in messages[0]["headers"]
        assert (b"cache-control", b"private, no-store") in messages[0]["headers"]
        assert calls == ["/pages/"]
        await app({**page, "path": "/api/send", "method": "POST"}, None, send)
        assert calls == ["/pages/", "/api/send"]
        release.set()
        await task

    asyncio.run(run())


@pytest.mark.parametrize("version,method", [("1.1", "HEAD"), ("2", "GET")])
def test_busy_response_obeys_http_framing(version, method):
    messages = []

    async def send(message):
        messages.append(message)

    asyncio.run(unavailable({"http_version": version, "method": method}, send))
    assert ((b"connection", b"close") in messages[0]["headers"]) == (version == "1.1")
    assert bool(messages[1]["body"]) == (method != "HEAD")


def test_disabled_gate_is_available_for_controlled_baseline(settings):
    settings.MANTECATO_PUBLIC_URL = ""
    settings.ANALYTICS_MAX_CONCURRENT = 0
    from mantecato.asgi import create_application

    assert create_application().__name__ == "application"


def test_gate_is_disabled_in_the_shipped_configuration():
    # Read the real default in a fresh process, not an override_settings value.
    env = {key: value for key, value in os.environ.items() if key != "ANALYTICS_MAX_CONCURRENT"}
    result = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import dotenv; dotenv.load_dotenv = lambda *args, **kwargs: None; "
            "from mantecato.settings import ANALYTICS_MAX_CONCURRENT; "
            "print(ANALYTICS_MAX_CONCURRENT)",
        ],
        env=env,
        text=True,
    )
    assert result.strip() == "0"


@pytest.mark.parametrize("capacity", [1, 2])
def test_waiters_are_fifo_and_cannot_be_overtaken_after_release(capacity):
    async def run():
        gate = AnalyticsGate(capacity, 8, 1)
        order = []
        holders = [gate.slot() for _ in range(capacity)]
        for holder in holders:
            assert await holder.__aenter__()

        async def request(label):
            async with gate.slot() as admitted:
                assert admitted
                order.append(label)
                await asyncio.sleep(0)

        tasks = []
        for index in range(4):
            tasks.append(asyncio.create_task(request(index)))
            await asyncio.sleep(0)
        for holder in holders:
            await holder.__aexit__(None, None, None)
        # Enter synchronously before the already-woken waiters resume. The
        # released slots must stay reserved, even though running is now zero.
        await request("newcomer")
        await asyncio.gather(*tasks)
        assert order == [0, 1, 2, 3, "newcomer"]
        assert gate.running == gate.waiting == 0

    asyncio.run(run())


def test_cancelling_a_woken_waiter_hands_its_reserved_slot_to_the_next():
    async def run():
        gate = AnalyticsGate(1, 2, 1)
        holder = gate.slot()
        await holder.__aenter__()
        completed = []

        async def request(label):
            async with gate.slot() as admitted:
                assert admitted
                completed.append(label)

        first = asyncio.create_task(request("first"))
        await asyncio.sleep(0)
        second = asyncio.create_task(request("second"))
        await asyncio.sleep(0)
        await holder.__aexit__(None, None, None)
        first.cancel()  # Its semaphore slot is reserved, but not consumed yet.
        with pytest.raises(asyncio.CancelledError):
            await first
        await second
        async with gate.slot() as admitted:
            assert admitted
        assert completed == ["second"]
        assert gate.running == gate.waiting == 0

    asyncio.run(run())


@pytest.mark.parametrize(
    "values", [(0, 1, 1), (1, -1, 1), (1, 1, 0), (1, 1, float("nan")), (1, 1, float("inf"))]
)
def test_invalid_limits_fail_fast(values):
    with pytest.raises(ValueError):
        AnalyticsGate(*values)
