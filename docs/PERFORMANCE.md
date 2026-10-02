# Lightweight operation and recovery

Mantecato uses Django, PostgreSQL and one terminating daily maintenance job.
No queue, Redis, Celery or additional web workers are needed for visitor rollup.
This guide contains only generic operating instructions and synthetic benchmark
results, not deployment identifiers or real traffic.

## Separate collection from maintenance

Tracking persists the event before best-effort visitor-state folding. HTTP ingest
never performs historical rollup, salt cleanup or digest expiry. Web deployment
runs migrations and any explicitly configured bootstrap hooks, not maintenance.

Run `run_daily_maintenance` separately each day (visitor rollup plus independent
AI authentication/audit cleanup). `rollup_visitors` remains available for targeted recovery. On Railway explicitly select
`/railway.rollup.toml` on a new cron service; see [Railway setup](RAILWAY.md#e-daily-maintenance-required).
Other hosts need an equivalent external scheduler. The manifest alone creates
nothing and does not configure the web service's schedule.

Maintenance uses set-based PostgreSQL aggregation and additive upserts. Each
complete `(website, finished period)` is one transaction: aggregate increments
and source-state deletion either both commit or both roll back. A retry resumes
unfinished units rather than repeating committed contributions. Import/backfill
and rollup share an advisory lock; the job reports busy instead of waiting on it.
Do not run a backfill or reimport as a general recovery step.

The open month and still-open legacy periods are excluded. Malformed period keys
are warned about and retained. Scope-only periods are handled; expired salts are
removed only when no site's day or scope state remains. Retention is independent:
batched updates NULL only event digests older than 396 days, never event rows.
Each retention batch also takes the shared nonblocking backfill lock and commits
separately. A busy lock leaves the next batch untouched and reports any earlier
committed batches; aggregation failure does not roll back completed retention.

## Bounded commands and observability

```bash
# Replace YYYY-MM with a finished calendar month, UUID with a site identifier.
uv run python manage.py rollup_visitors --period YYYY-MM --website UUID --dry-run
uv run python manage.py rollup_visitors --max-runtime 900 --sql-timeout-ms 60000
```

Dry-run does not modify state, counters, salts or digests. Site selection applies
to retention too; period selection applies to rollup/salt cleanup, not the digest
age cutoff. Runtime is checked between atomic units and retention batches, with
transaction-local SQL/lock timeouts. Diagnostic queries have separate short
limits: the runtime budget is not a hard process-kill deadline.

JSON summaries report duration, committed units/rows, remaining units, expired
digests and whether retention is still pending. `completed` and `dry_run` exit
successfully; `busy` and `budget_exhausted` exit 2; real errors exit 1. Logs do not
include salts, visitor digests, API credentials or SQL parameters.

Alert on missing daily success, failures and a persistent finished-period or
retention backlog. Check privacy enforcement operationally: a failed scheduler
cannot guarantee timely salt destruction or digest expiry.

`QUERY_SUMMARY_LOG=False` is the production default; opt in only while diagnosing.
DEBUG retains Server-Timing support. Existing slow-query/error diagnostics remain
available. Gunicorn access logs omit URLs/query strings, IPs and User-Agent values;
check upstream/platform log retention separately.

## Read and write efficiency

Count-only API requests avoid session windows and unused distincts. Totals reuse
their returned aggregation; breakdown totals stay independent, especially for
overlapping content groups. API `daily_unique_visitors` and dashboard monthly
uniques remain different metrics.

Dashboard session totals, landings and visit buckets return SQL aggregates rather
than event lists, visitor sets or large start-event `IN` lists. Content-group
uniques are grouped in SQL. Hidden page/channel panels load on demand, queue
concurrent selections instead of dropping them, and retain their results only
within the current page. Realtime queries only its three
visible datasets, pauses in hidden tabs, drops overlapping polls and backs off
on failures. Authorization and API-key revocation are not cached.

Visitor-state pageviews use an atomic upsert; engagement uses a conditional atomic
update. The tracker keeps its 15-second heartbeat, while avoiding duplicate sends
of identical cumulative seconds on visibility/pagehide. Failed sends can retry
on the next heartbeat or lifecycle event, including while hidden; late failures
from earlier pages cannot reset a newer page's deduplication. GPC/DNT behaviour and
metric formulas are unchanged, including the historical integer-gap boundary
for dashboard totals/landings and the bucket counter's timestamp comparison.

No shared aggregate cache, analytics index/table, partitioning, connection pool or
heartbeat-interval change is introduced without a measured need. Optional AI
connections add four authentication/audit models only; no analytics schema changes.

## Remote MCP runtime

Gunicorn 26's native ASGI worker hosts Django and the official stateless MCP v1
transport in one service. Keep-alive is disabled after isolated persistent-socket
stalls. HTTP/1 responses also explicitly advertise `Connection: close`, avoiding
client socket-reuse races under concurrent load. A reentrant per-request thread
context closes Django ORM sockets even on disconnect/cancellation, in addition to
explicit MCP cleanup. These workarounds are not a production throughput guarantee.
HTTP connections
are bounded at 16 per worker, Django persistent connections are disabled, and
synchronous MCP database work closes its connections explicitly off the event loop.
One MCP tool query runs per worker, using existing read-only v1 services and SQL
budgets. No self-HTTP, additional queue or provider/model process is introduced.

MCP/OAuth becomes available when the canonical public URL is configured. Before
public configuration, measure unconfigured/configured ASGI, authenticated MCP and
concurrent collection/maintenance under the intended resource limits. Include
settings/auth query counts, connection peaks and RSS/CPU; localhost smoke tests cannot
establish the <500 ms p95 collector target or provider interoperability. See
[AI connections](AI-CONNECTIONS.md) for security and operational gates.

## Reproduce the synthetic benchmark

Use a **dedicated empty local PostgreSQL test database**, never production or a
local tunnel to production. Its name must start with `test_` or end with `_test`.
The script rejects remote hosts and nonempty event/state/aggregate tables. Configure
`DATABASE_URL` explicitly for that database, apply migrations, then run:

```bash
uv run python manage.py migrate
uv run python tools/benchmark_analytics.py --visitors 1000 --output /tmp/analytics-benchmark.json
```

The fixture uses random synthetic site identifiers, 1,000 visitor states, 2,000
pageviews and 13,000 scope rows (12 content groups per visitor). It removes its own
site data afterward. It reports query count, wall/SQL time, process CPU time and
process-wide peak RSS in the platform's native units. Database CPU/RAM are not
included in Python process measurements.

Illustrative measurements on local PostgreSQL 16, same fixture. The reference
baseline is one run; the optimized values are medians of five separate runs
(query counts were identical across those runs). Repeat the script on the same
empty test database to check variability.

| Operation | Before: queries / wall time | After: queries / median wall time |
| --- | ---: | ---: |
| Finished-period rollup | 56,019 / 4,843 ms | 28 / 199 ms |
| API pageview totals | 2 / 8.59 ms | 1 / 0.91 ms |
| API visit totals | 2 / 7.74 ms | 1 / 4.30 ms |
| Dashboard session totals | 1 / 4.27 ms | 1 / 3.21 ms |
| 100 synthetic ingests | 404 / 61.18 ms | 301 / 38.71 ms |
| 100 engagement updates | 200 / 32.63 ms | 100 / 7.81 ms |

These are **not production SLAs, HTTP percentiles or constrained-resource load
results**. Dashboard session SQL takes more database time than the earlier event
scan, while reducing Python transfer/work. The fixture concentrates historical
events in one day; 1/7/30/365-day dashboard measurements are smoke tests, not
representative year-long traffic. The realtime fixture is deliberately empty.

Before relying on resource or latency targets, run a representative isolated
staging workload: repeated 1/7/30/365-day dashboards, active realtime, count-only
versus session API queries, ingest/engagement, and concurrent maintenance. A small
reference envelope is 2 CPU/2 GB web and 1 CPU/1 GB database. Measure HTTP p50/p95/p99,
per-query EXPLAIN/temporary I/O, transferred rows, locks, CPU and RSS on both
services. Verify exact results and aim for representative ingest/script/OPTIONS
p95 below 500 ms under maintenance load. Do not trade lower Python usage for an
unmeasured database bottleneck. Larger SQL section aggregation, extra request-local
reuse and any schema/infrastructure changes remain measurement-driven follow-ups.

## Synthetic ASGI/MCP compatibility check

`tools/benchmark_ai_connections.py` requires empty analytics tables on an explicitly
configured **socket-only test PostgreSQL** database. It creates and deletes its own
synthetic site/account, exercises 80 collector POSTs, 80 script GETs and 80 preflights
per mode, then adds 20 MCP queries and concurrent maintenance over 1,000 historical
visitor states and 12,000 group states. It never connects provider accounts.

```bash
uv run --with psutil python tools/benchmark_ai_connections.py --output /tmp/ai-http.json
```

One illustrative local run with two workers, eight client HTTP connections and
**current code/settings in every mode** (including `CONN_MAX_AGE=0`):

| Runtime | Collector p95 | Script p95 | OPTIONS p95 | Maximum sampled worker RSS |
| --- | ---: | ---: | ---: | ---: |
| WSGI, AI off | 327 ms | 326 ms | 326 ms | 73 MB |
| ASGI, AI off | 291 ms | 287 ms | 288 ms | 75 MB |
| ASGI + MCP + offline maintenance | 321 ms | 320 ms | 320 ms | 102 MB |

These client-side burst measurements **include connection-pool queue waiting**;
they are neither server-only latency nor a comparison with a particular deployed
revision. All 240 synthetic collector POSTs persisted across the three modes.
MCP p95 was 109 ms; after each mode web DB sockets returned to zero (only the
benchmark observer remained). This verifies local compatibility and lifecycle,
not peak resource guarantees. Repeat runs and representative resource-capped
staging, database CPU/RAM, SQL EXPLAIN/temp I/O and 24-hour monitoring remain
necessary before a public rollout. Do not infer a guaranteed <500 ms p95 SLA.

## Safe rollout and recovery

Confirm a restorable backup, deployed revision and rollback path before any
production operation. Release collection/startup isolation without waiting for a
historical backlog to finish. Verify health, script delivery, preflight/CORS and
authenticated analytics reads; health alone does not establish successful tracking.

Release the matching offline job separately. Dry-run a chosen finished period,
inspect the backlog, then authorize targeted maintenance. Compare traffic through
the authenticated CLI/API, not ad-hoc production SQL. Do not infer lost pageviews
from failed HTTP requests alone: event insertion and response success are separate.
Monitor collection latency, errors, DB load, job completion and backlog for at least
24 hours. Avoid raising web timeouts/worker counts to hide synchronous maintenance.

Pushes, deployments, service creation and production maintenance writes are
separate operator actions, not effects of installing or testing this repository.
