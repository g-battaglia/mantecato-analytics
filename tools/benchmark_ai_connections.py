"""Synthetic, local-only HTTP/runtime check, not a constrained-resource SLA.

Run on an empty socket PostgreSQL test DB after migrations:
    uv run --with psutil python tools/benchmark_ai_connections.py --output /tmp/ai-http.json
"""

import argparse
import asyncio
import json
import logging
import os
import socket
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mantecato.settings")
import django

django.setup()

import httpx2 as httpx  # noqa: E402
from django.conf import settings  # noqa: E402
from django.db import connection, transaction  # noqa: E402
from django.utils import timezone  # noqa: E402
from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

from apps.ai_connections.models import AIConnection, OAuthClient  # noqa: E402
from apps.ai_connections.policy import create_connection, issue  # noqa: E402
from apps.core.models import (  # noqa: E402
    MantecatoUser,
    VisitorDaily,
    VisitorDayState,
    VisitorPeriod,
    VisitorScopeState,
    Website,
    WebsiteEvent,
)
from mantecato.memory import MemorySampler  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--worker-connections", type=int, default=16)
    parser.add_argument("--analytics-concurrency", type=int, default=1)
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--sample-interval", type=float, default=0.25)
    parser.add_argument("--database-pid", type=int, help="Optional dedicated local DB root PID")
    args = parser.parse_args()
    if (
        args.workers < 1
        or args.worker_connections < 1
        or args.cycles < 1
        or args.analytics_concurrency < 0
        or not 0.1 <= args.sample_interval <= 10
        or (args.database_pid is not None and args.database_pid < 1)
    ):
        parser.error("Invalid worker, concurrency, cycle, sampling or PID argument")
    # Synthetic DEBUG=True is needed for loopback MCP HTTP, but client debug
    # traces add large logs and distort the memory experiment.
    for name in ("httpx", "httpcore", "httpx2", "httpcore2", "asyncio"):
        logging.getLogger(name).setLevel(logging.WARNING)
    db = connection.settings_dict
    host = db.get("OPTIONS", {}).get("host") or db.get("HOST")
    if (
        not host
        or not host.startswith("/")
        or not (db["NAME"].startswith("test_") or db["NAME"].endswith("_test"))
    ):
        parser.error("Requires explicitly isolated socket PostgreSQL test database")
    analytics_models = [
        WebsiteEvent,
        VisitorDayState,
        VisitorScopeState,
        VisitorDaily,
        VisitorPeriod,
    ]
    if any(model.objects.exists() for model in analytics_models):
        parser.error("Requires empty analytics tables")
    user = MantecatoUser.objects.create_user(
        username="synthetic-" + os.urandom(6).hex(), password=None
    )
    site = Website.objects.create(
        user_id=user.pk, name="Synthetic runtime benchmark", domain="https://example.test"
    )
    results = {}
    client_ids = []

    def seed():
        start = (
            timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            - timedelta(days=1)
        ).replace(day=1)
        VisitorDayState.objects.bulk_create(
            [
                VisitorDayState(
                    website_id=site.pk,
                    day=start.date(),
                    period=start.strftime("%Y-%m"),
                    visitor_key=str(i),
                    first_seen=start,
                    last_seen=start + timedelta(seconds=20),
                    total_pageviews=2,
                    cur_visit_pageviews=2,
                    cur_visit_duration_s=20,
                    entry_path=f"/synthetic/{i}",
                )
                for i in range(1000)
            ]
        )
        VisitorScopeState.objects.bulk_create(
            [
                VisitorScopeState(
                    website_id=site.pk,
                    period=start.strftime("%Y-%m"),
                    visitor_key=str(i),
                    scope="group",
                    scope_value=f"tag:{g}/synthetic/{i}",
                )
                for i in range(1000)
                for g in range(12)
            ]
        )
        WebsiteEvent.objects.bulk_create(
            [
                WebsiteEvent(
                    website_id=site.pk,
                    visitor_key=str(i),
                    url_path=f"/synthetic/{i}",
                    created_at=start,
                )
                for i in range(1000)
                for _ in range(2)
            ]
        )

    def run(mode):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        raw = None
        env = {
            **os.environ,
            "DEBUG": "True",
            "MANTECATO_PUBLIC_URL": origin if mode == "mixed" else "",
            "CONN_MAX_AGE": "0",
            "SECURE_SSL_REDIRECT": "False",
            "ANALYTICS_MAX_CONCURRENT": str(args.analytics_concurrency),
        }
        if mode == "mixed":
            settings.DEBUG = True
            settings.MANTECATO_PUBLIC_URL = origin
            with transaction.atomic():
                client = OAuthClient.objects.create(
                    client_id="synthetic:" + os.urandom(16).hex(),
                    name="Benchmark",
                    redirect_uris=[],
                )
                client_ids.append(client.pk)
                conn = create_connection(
                    user, client, "personal", [str(site.pk)], ["analytics:read"], timedelta(days=1)
                )
                raw = issue(
                    "personal",
                    {"resource": origin + "/mcp", "scopes": conn.scopes},
                    timedelta(days=1),
                    conn,
                )
            seed()
        worker = "sync" if mode == "wsgi" else "asgi"
        app = "mantecato.wsgi:application" if mode == "wsgi" else "mantecato.asgi:application"
        print("runtime=" + mode, flush=True)
        with args.output.with_suffix("." + mode + ".log").open("w+") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "gunicorn",
                    app,
                    "--worker-class",
                    worker,
                    "--workers",
                    str(args.workers),
                    "--worker-connections",
                    str(args.worker_connections),
                    "--keep-alive",
                    "0",
                    "--forwarded-allow-ips",
                    "",
                    "--graceful-timeout",
                    "2",
                    "--bind",
                    f"127.0.0.1:{port}",
                ],
                env=env,
                stdout=log,
                stderr=log,
            )
            job = None
            # Include master, every worker and the terminating job throughout
            # startup/workload/cleanup. DB attribution is opt-in and explicit.
            sampler = MemorySampler(
                lambda: (
                    (process.pid,)
                    + ((job.pid,) if job is not None else ())
                    + ((args.database_pid,) if args.database_pid else ())
                ),
                interval=args.sample_interval,
            )
            sampler.__enter__()
            measurements = {path: [] for path in ("/api/send", "/api/script", "OPTIONS", "MCP")}
            try:
                for _ in range(100):
                    try:
                        if httpx.get(origin + "/health/", timeout=1).status_code == 200:
                            break
                    except httpx.HTTPError:
                        time.sleep(0.05)
                else:
                    raise RuntimeError("Local worker startup failed")

                async def workload(session=None):
                    nonlocal job
                    if session:
                        job = subprocess.Popen(
                            [
                                sys.executable,
                                "manage.py",
                                "run_daily_maintenance",
                                "--rollup-runtime",
                                "10",
                                "--ai-runtime",
                                "10",
                            ],
                            env=env,
                            stdout=log,
                            stderr=log,
                        )
                    async with httpx.AsyncClient(
                        timeout=20,
                        limits=httpx.Limits(max_connections=8),
                        headers={
                            "User-Agent": (
                                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                                "Chrome/130.0.0.0 Safari/537.36"
                            )
                        },
                    ) as client:

                        async def request(i):
                            kind = list(measurements)[i % 3]
                            before = time.perf_counter()
                            if kind == "/api/send":
                                response = await client.post(
                                    origin + kind,
                                    json={
                                        "type": "event",
                                        "payload": {
                                            "website": str(site.pk),
                                            "url": "/synthetic-collector",
                                            "hostname": "example.test",
                                            "title": "Synthetic",
                                        },
                                    },
                                )
                            elif kind == "OPTIONS":
                                response = await client.options(
                                    origin + "/api/send",
                                    headers={
                                        "Origin": "https://example.test",
                                        "Access-Control-Request-Method": "POST",
                                    },
                                )
                            else:
                                response = await client.get(origin + kind)
                            assert response.status_code in (200, 204)
                            measurements[kind].append((time.perf_counter() - before) * 1000)

                        async def tools():
                            if session:
                                for _ in range(20):
                                    before = time.perf_counter()
                                    result = await session.call_tool(
                                        "query_metrics",
                                        {
                                            "website_id": str(site.pk),
                                            "metrics": ["pageviews"],
                                            "range": "30d",
                                        },
                                    )
                                    assert not result.is_error, result.content
                                    measurements["MCP"].append(
                                        (time.perf_counter() - before) * 1000
                                    )

                        for cycle in range(args.cycles):
                            # Keep the original 20 tools total: repeated short
                            # cycles must not bypass the real per-worker quota.
                            await asyncio.gather(
                                asyncio.gather(*(request(i) for i in range(240))),
                                tools() if cycle == 0 else asyncio.sleep(0),
                            )

                async def scenario():
                    if not raw:
                        return await workload()
                    async with (
                        httpx.AsyncClient(
                            headers={"Authorization": "Bearer " + raw}, timeout=20
                        ) as client,
                        streamable_http_client(origin + "/mcp", http_client=client) as (
                            read,
                            write,
                        ),
                        ClientSession(read, write) as session,
                    ):
                        await session.initialize()
                        await workload(session)

                asyncio.run(scenario())
                if job:
                    assert job.wait(timeout=20) == 0
                time.sleep(0.5)  # Allow response-finalization DB cleanup to finish.
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
                    )
                    remaining_connections = cursor.fetchone()[0]
                    assert remaining_connections == 1, "Web database connections leaked"
                    results[mode] = {"database_connections_after": remaining_connections}
                try:
                    import psutil

                    workers = psutil.Process(process.pid).children()
                    results[mode]["worker_rss_mb"] = [
                        round(worker.memory_info().rss / 1024**2, 1) for worker in workers
                    ]
                    results[mode]["worker_cpu_seconds"] = [
                        round(sum(worker.cpu_times()[:2]), 3) for worker in workers
                    ]
                except ImportError:
                    pass
                for path, values in measurements.items():
                    if not values:
                        continue
                    values.sort()
                    results[mode][path] = {
                        "requests": len(values),
                        **{
                            f"p{p}_ms": round(
                                values[min(len(values) - 1, int(len(values) * p / 100))], 2
                            )
                            for p in (50, 95, 99)
                        },
                    }
            finally:
                sampler.__exit__(None, None, None)
                results.setdefault(mode, {})["memory"] = sampler.result
                results[mode]["memory"]["includes_database"] = bool(args.database_pid)
                results[mode]["configuration"] = {
                    "workers": args.workers,
                    "worker_connections": args.worker_connections,
                    "analytics_concurrency": args.analytics_concurrency,
                    "cycles": args.cycles,
                }
                if job and job.poll() is None:
                    job.terminate()
                    job.wait(timeout=10)
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

    try:
        for mode in ("wsgi", "asgi", "mixed"):
            run(mode)
        results["synthetic_pageviews"] = WebsiteEvent.objects.filter(
            website_id=site.pk, url_path="/synthetic-collector"
        ).count()
        assert results["synthetic_pageviews"] == 240 * args.cycles
        args.output.write_text(json.dumps(results, indent=2))
        print(json.dumps(results, indent=2))
    finally:
        AIConnection.objects.filter(user=user).delete()
        OAuthClient.objects.filter(client_id__in=client_ids).delete()
        user.delete()
        for model in analytics_models:
            model.objects.filter(website_id=site.pk).delete()
        site.delete()


if __name__ == "__main__":
    main()
