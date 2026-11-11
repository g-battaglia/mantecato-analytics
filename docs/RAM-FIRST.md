# RAM-first operation

The priority is less **total web + database + job memory**, not just faster SQL.
Do not add a resident cache, workers or another service to make one chart look
better. Keep collection, remote MCP, exact metrics, privacy and durability intact.

## Included in this release

- Section visitor counts return SQL aggregates, not per-event digests accumulated
  in Python sets. Normalization, Unicode digits (including C-locale databases),
  depth, filters and historical retention rules have differential tests.
- The browser overview skips two unused live datasets. Country table/map share
  one small result, retaining their separate empty-country and denominator rules.
  Legacy API live detail fields remain available.
- A process-local **ASGI** analytics gate runs before ORM threads are allocated.
  Dashboard, legacy/v1 analytics and MCP share the budget. Defaults:
  `ANALYTICS_MAX_CONCURRENT=1`, `ANALYTICS_MAX_WAITING=4`,
  `ANALYTICS_WAIT_SECONDS=5`. Saturation returns 503, `Retry-After: 1` and private
  no-store headers. Collector, OPTIONS, health, static and auth bypass the gate.
  Clients must treat analytics overload as a retryable failure, not empty data.
  This is not a distributed quota; WSGI does not have this ASGI gate. Custom
  dashboard widgets queue in the browser, with an explicit accessible retry
  state for failed/overloaded fragments instead of an endless loading spinner.
- Dependencies are refreshed, including **Django 6.1.3, Gunicorn 27.0.0 and MCP
  SDK 2.3.0**. The SDK migration preserves stateless JSON transport, body limits,
  origin/host allowlists, scopes and read-only tool annotations. Keep-alive and
  ORM-cleanup workarounds remain. See [dependency maintenance](DEPENDENCIES.md).
- Read-only memory diagnostics and bounded continuous sampling for benchmarks.
  Diagnostics/admission use the standard library and existing Django/ASGI APIs;
  no cache daemon, connection pool, schema/index or external service is added.

Production Railway resource/worker defaults are deliberately unchanged: a local
experiment is not approval to lower a production memory limit. Frontend asset
compilation and database tuning remain separate follow-ups, not claimed RAM wins.

## Diagnose before changing limits

Inside the target container, the smallest report avoids Django startup entirely:

```sh
python -m mantecato.memory --pid 1
# Or management-command JSON lines; Django itself adds observer overhead:
python manage.py memory_report --pid 1 --samples 20 --interval 0.25
# Optional three-second, read-only database metadata snapshot (no query text):
python manage.py memory_report --pid 1 --database
```

Select the actual master PID if it is not PID 1. Reports contain process IDs,
thread counts, numeric memory counters and no command lines, environment values,
credentials, visitor digests or analytics. No DB access occurs without --database.

- `process_totals.rss_bytes` **double-counts shared pages**. Linux PSS and private
  bytes offer better attribution. Missing/denied counters are null, not zero.
- `observer_cgroup.current_bytes` covers every member of the observer's cgroup,
  not necessarily just selected PIDs. A local development cgroup can include
  unrelated work; a web cgroup does not include a separately deployed DB.
- `memory.stat.file` already includes shmem: do not add them. Do not automatically
  subtract all file cache as guaranteed free. Compare anon, inactive_file,
  pressure, events/OOM and Railway's graph. Railway does not fully specify its
  cache-accounting formula, so verify it against the container.
- A cgroup lifetime peak can predate an experiment. The sampler's peak of current
  usage is separate. Sampling can miss short bursts; sampling_errors explicitly
  flags failed observations. Max per-worker RSS is not a project total.
- PostgreSQL shared_buffers is mapped by multiple processes. Summing backend RSS
  and then adding shared_buffers again is not physical RAM accounting.
- Virtual stack reservations are not resident RAM. A falling RSS after worker
  recycling is not proof that the leak/high-water cause was fixed.

## Reproduce experiments safely

Use only an explicitly configured **dedicated empty local PostgreSQL test DB**
whose name starts with test_ or ends with _test. Apply migrations first. Never use
production, a Railway tunnel, or a development database containing real events.
The scripts reject remote/non-test/nonempty analytics databases and remove their
own synthetic fixtures. Run serially, with no other load on that test DB.

```sh
# Existing collector/MCP/maintenance fixture, with bounded peak sampling:
python tools/benchmark_ai_connections.py --workers 2 --worker-connections 16 \
  --cycles 5 --output /tmp/ram-2.json
python tools/benchmark_ai_connections.py --workers 1 --worker-connections 8 \
  --cycles 5 --output /tmp/ram-1.json
# Try 1x16 separately if the 1x8 collector latency is unacceptable.
# --analytics-concurrency 0 explicitly disables admission for a baseline run.

# 400k synthetic pageviews, 200k visitors, fresh interpreter per strategy:
python tools/benchmark_section_memory.py --visitors 200000 \
  --output /tmp/section-ram.json

python tools/benchmark_analytics.py --visitors 1000 --output /tmp/analytics.json
```

The HTTP script requires a local Unix-socket test DB and uses DEBUG for loopback
HTTP MCP compatibility, not production-equivalent security settings. Repeated
collector cycles keep the original 20 MCP calls total to respect real rate limits.
Use --database-pid with a **dedicated local DB master** to include its process tree
in any of these scripts; otherwise DB memory is explicitly not included. In
separate Railway containers collect each service's counters simultaneously.

### Final-stack local results (not Railway validation)

One serial macOS / PostgreSQL 18 run, Django 6.1.3 / Gunicorn 27.0.0 / MCP SDK
2.3.0, five collector cycles per mode,
240 total synthetic HTTP requests/cycle, eight client connections, 20 MCP tools
and a terminating maintenance job in mixed mode. Both worker configurations use
the same updated code and analytics admission limit. This comparison does not
isolate every code change against the original release.

| ASGI configuration | After-workload web RSS sum | Sampled peak web + job RSS sum | Collector p95 | Script p95 |
| --- | ---: | ---: | ---: | ---: |
| 2 workers, 16 connections each, MCP off | 200.2 MiB | 200.2 MiB | 368 ms | 348 ms |
| 1 worker, 16 connections, MCP off | 126.3 MiB | 126.3 MiB | 364 ms | 359 ms |
| 2 workers, 16 connections each, MCP + maintenance | 272.3 MiB | 337.8 MiB | 407 ms | 403 ms |
| 1 worker, 16 connections, MCP + maintenance | 162.2 MiB | 225.3 MiB | 474 ms | 467 ms |

All 1,200 collector events per configuration persisted. Connections returned to
the observer-only baseline after each mode. These are RSS sums (no macOS PSS),
not private memory. DB is excluded from this HTTP table. Percentiles include
client-pool waiting. The 1x16 candidate reduces observed warm web RSS by ~40% in
mixed mode, but collector p95 rises by ~67 ms. MCP p95 is ~180 ms. This is **not
production validation**: repeat with realistic rates and Linux resource caps.

Before the full dependency refresh, Django 6.0.5 / Gunicorn 26.2.0 / SDK 1.30
showed 244.4 -> 148.6 MiB warm web RSS for 2x16 -> 1x8, with mixed collector p95
469 -> 517 ms. Do not attribute those pre-refresh measurements to the final
stack, or assume dependency upgrades themselves save RAM.

For the sections fixture (400k rows / 200k unique visitors), with transaction-local
work_mem=1MB and no query parallel workers, counts were identical:

| Strategy | Process lifetime peak RSS | Wall time incl. sampled observer |
| --- | ---: | ---: |
| Previous Python iterator + sets | 100.3 MiB | 578 ms |
| SQL section DISTINCT | 63.3 MiB | 1,505 ms |

The final SQL uses a streaming subquery barrier to avoid evaluating the costly
normalizer twice, without forcing a MATERIALIZED event relation. The preceding
inlined version took ~2,530 ms on the same-size fixture.

The sampled combined **process + DB RSS sums** were 428.0 vs 454.0 MiB: they do
**not** demonstrate any whole-system reduction in that run. PostgreSQL cache/shared-page accounting
and sequential fixture effects require Linux PSS/cgroup confirmation. The result
supports bounded Python allocations, **not** a claim of a drastic project-wide
reduction. The SQL CPU/I/O trade-off is real and must stay visible.

## Promotion gates and next experiments

1. Reproduce cold/warm and 1/7/30/365-day dashboards, high distinct cardinality,
   collector, authenticated MCP and maintenance; repeat for 24–48 h including
   nightly work. Sample web/DB/job concurrently, including deployment overlap.
2. Candidate variables in **staging only**: GUNICORN_WORKERS=1 and
   GUNICORN_WORKER_CONNECTIONS=8 or 16. Keep CONN_MAX_AGE=0, no pool and no preload
   as baseline. Analytics gate values are per process and multiply with workers.
3. Investigate PostgreSQL's real settings, connections, autovacuum, temp I/O and
   nightly WAL/memory peaks. Bound sort/hash/maintenance and parallel concurrency
   before reducing the DB limit. Example starting experiments for a 512 MiB DB:
   shared_buffers 64–128 MiB, work_mem 1–4 MiB, explicit hash/maintenance budgets;
   these are **not** settings automatically applied by this release. Keep
   autovacuum, backups, fsync and commit durability enabled.
4. SQL aggregation is not free: inspect EXPLAIN/temporary-file I/O and total memory.
   Prefer a bounded spill or fewer simultaneous sorts over a huge in-memory hash.
   Add indices only with evidence; account for write/WAL/cache cost as well.
5. Verify the separate daily scheduler actually exists (a manifest alone creates
   nothing). Recover backlog in bounded terminating jobs, avoiding nightly backup
   overlap. Do not reimport/backfill as a general recovery step.
6. If Linux/glibc shows allocator fragmentation, test MALLOC_ARENA_MAX=2 separately.
   It does not change Python pymalloc and may increase CPU contention. Do not
   force gc/malloc_trim per request or hide a leak with frequent worker restarts.
7. MCP remains enabled when configured. Removing it or changing exact metrics,
   retention or feature availability requires an explicit product decision.

Aspirational budgets remain >=50–60% less web RAM and >=50% less total working
memory, without collection regressions. **They are not established by these local
results.** Do not lower Railway RAM limits, add cache/replicas, or claim success
until the comparable whole-service measurements and correctness gates pass.
Rollback: restore the prior code/runtime; ANALYTICS_MAX_CONCURRENT=0 permits a
controlled admission baseline, but does not undo SQL or runtime changes.
