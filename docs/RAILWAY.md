# Deploy Mantecato on Railway

This guide explains how to deploy Mantecato on [Railway](https://railway.com) and how to
publish your own copy as a **community template** (the "Deploy on Railway" button).

Mantecato ships a [`railway.toml`](../railway.toml) at the repo root. Railway reads it
automatically and builds the app with **Railpack** (the modern default builder, successor to
Nixpacks), which natively detects `uv.lock` + `pyproject.toml` + `manage.py` and runs `uv sync`.

What the config does:

- **Build** — `collectstatic` runs at build time (Railpack does not do it for you), so WhiteNoise's
  manifest storage works in production.
- **Pre-deploy** — `migrate` runs once, before the new version receives traffic. The umami hook
  (`importumamienv`) and the optional admin bootstrap (`createuser`) run here too.
  Visitor maintenance is deliberately absent: provision the separate daily job in section E.
- **Start** — Gunicorn 26 serves `mantecato.asgi:application` with native lifespan, 16
  connections per worker and keep-alive disabled on Railway's injected `$PORT`.
- **Health check** — Railway probes `/health/`, which runs `SELECT 1` against PostgreSQL.

> **Heads up — config as code only covers one service.** Unlike `render.yaml`, a Railway
> `railway.toml` describes *only the build and deploy of a single service*. It does **not** provision
> the database or the environment variables. Those live on the Railway side (dashboard / CLI) and,
> for a reusable template, are baked into the template itself (see below).

> **Why Railpack and not the Dockerfile?** Railway automatically builds with a
> root file named `Dockerfile` and ignores the `builder` setting. To keep Railway
> on **Railpack**, the image used for Docker self-hosting is named
> [`Dockerfile.standalone`](../Dockerfile.standalone) — Railway does not
> auto-detect that name, so `railway.toml`'s `builder = "RAILPACK"` takes effect.
> Docker Compose (`docker compose up`) is unaffected.

---

## A. Environment variables

Set these on the **web service** in your Railway project. The "Template value" column uses Railway
[reference variables](https://docs.railway.com/reference/variables) (`${{ ... }}`) and
[template variable functions](https://docs.railway.com/templates/create#template-variable-functions),
which are resolved when the template is deployed.

| Variable | Template value | Required | Notes |
|---|---|:---:|---|
| `SECRET_KEY` | `${{secret(50)}}` | ✅ | Django signing key. `get_secret_key()` raises `ImproperlyConfigured` if missing. `secret(50)` generates a fresh 50-char key per deploy. |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | ✅ | Reference to the project's Postgres service. |
| `DEBUG` | `False` | ✅ | Enables WhiteNoise compressed-manifest storage, secure cookies, HSTS. |
| `DJANGO_SETTINGS_MODULE` | `mantecato.settings` | ✅ | Explicit, so gunicorn/wsgi resolve settings reliably. |
| `ALLOWED_HOSTS` | `${{RAILWAY_PUBLIC_DOMAIN}}` | ✅ | Railway public domain (no scheme). Comma-separated list supported. |
| `CSRF_TRUSTED_ORIGINS` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` | ✅ | **Must** include the `https://` scheme — otherwise login POSTs fail with CSRF 403. |
| `USE_SECURE_PROXY_SSL_HEADER` | `True` | ✅ | Railway terminates TLS upstream. Without this, `SECURE_SSL_REDIRECT` causes an HTTPS redirect loop. Does not set the native MCP ASGI scheme. |
| `FORWARDED_ALLOW_IPS` | *(verified proxy IPs/CIDRs)* | AI | Environment allowlist read by Gunicorn and the MCP scheme adapter; absent means loopback only. Verify the TLS proxy trust boundary before enabling MCP. |
| `RAILPACK_PYTHON_VERSION` | `3.12` | ⚙️ | Pins the Python version. Railpack otherwise defaults to 3.13.x. |
| `GUNICORN_WORKERS` | `2` | – | Worker processes (tune to your plan's RAM). |
| `GUNICORN_TIMEOUT` | `120` | – | Worker timeout in seconds. |
| `GUNICORN_WORKER_CONNECTIONS` | `16` | – | Native ASGI HTTP connection bound per worker. |
| `CONN_MAX_AGE` | `0` | – | Required under ASGI; no persistent Django DB connections. |
| `MANTECATO_PUBLIC_URL` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` | AI | Canonical public origin; configuring it makes remote MCP/OAuth available. Leave unset when unused. |
| `TIME_ZONE` | `UTC` | – | e.g. `Europe/Rome`. |
| `LANGUAGE_CODE` | `en-us` | – | UI language. |
| `INIT_ADMIN_USER` | `admin` | – | Username of the first admin. |
| `INIT_ADMIN_PASS` | *(set yourself)* | – | If set, the pre-deploy step creates the admin **once**. Later deploys skip it safely. Leave empty to create the admin manually later. |
| `UMAMI_DATABASE_URL` | *(empty)* | – | Source Umami DB, only for migration. |
| `UMAMI_IMPORT_ON_DEPLOY` | `False` | – | Set `True` to run an import on deploy (then set back to `False`). |
| `UMAMI_IMPORT_MODE` | `data` | – | `data` is additive/idempotent; `full` also imports config. |
| `UMAMI_IMPORT_ALLOW_CONFIG` | `False` | – | Required `True` only for `full` imports. |

Plus a **PostgreSQL 16** service (Railway's official Postgres). Mantecato requires Postgres in
production; `DATABASE_URL` is consumed by `dj-database-url`.

---

## B. Deploy it yourself (project)

1. **New Project → Deploy from GitHub repo** → pick your `mantecato` fork. Railway reads
   `railway.toml` and selects Railpack.
2. **+ New → Database → Add PostgreSQL** (Postgres 16). The service becomes referenceable as
   `Postgres`.
3. On the **web service → Variables**, paste the values from the table above (use the reference
   variables `${{Postgres.DATABASE_URL}}`, `${{RAILWAY_PUBLIC_DOMAIN}}` and the function
   `${{secret(50)}}`).
4. **Settings → Networking → Generate Domain**, so `RAILWAY_PUBLIC_DOMAIN` exists.
5. Watch the deploy logs:
   - Railpack detects `uv` and runs `collectstatic` during build;
   - the pre-deploy step runs `migrate` (+ `importumamienv`, + `createuser` if `INIT_ADMIN_PASS` is set);
   - gunicorn starts on `$PORT`;
   - the `/health/` check returns `200`.
6. Open the generated HTTPS URL and log in.

---

## C. Publish it as a community template

A Railway template is **composed in the dashboard**, not stored as a file in the repo. After you have
a working project (section B):

1. Go to **Templates → New Template** (or "Create Template from Project"). Railway imports both
   services — the GitHub web service and Postgres — with their variables.
2. Review the variables so every deploy gets fresh, correct values:
   - secrets use **functions** — `SECRET_KEY` = `${{secret(50)}}`;
   - cross-service values use **references** — `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`,
     `ALLOWED_HOSTS` = `${{RAILWAY_PUBLIC_DOMAIN}}`, `CSRF_TRUSTED_ORIGINS` =
     `https://${{RAILWAY_PUBLIC_DOMAIN}}`;
   - mark `INIT_ADMIN_PASS` and the `UMAMI_*` vars as optional/empty.
   - Add a short description to each variable — Railway shows them in the deploy form.
3. Fill in the metadata: name (e.g. *Mantecato — Self-hosted Analytics*), description, category
   (*Analytics*), overview. Set visibility to **Public**.
4. **Publish**. Railway generates a template URL like `https://railway.com/template/XXXXXX` and the
   deploy button.
5. Update the badge URL in the project `README.md`, replacing `XXXXXX` with your real template id.

Publishing to the marketplace can earn kickbacks (up to 25% for open-source templates with active
community support).

---

## D. Operational notes

- **Custom domain.** The template defaults `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` to the Railway
  domain only. When you add a custom domain, append it to both:

  ```
  ALLOWED_HOSTS=yourdomain.com,${{RAILWAY_PUBLIC_DOMAIN}}
  CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://${{RAILWAY_PUBLIC_DOMAIN}}
  ```

- **Import from Umami.** Set `UMAMI_DATABASE_URL` and `UMAMI_IMPORT_ON_DEPLOY=True`, redeploy, then
  set `UMAMI_IMPORT_ON_DEPLOY=False`. Mode `data` (default) is idempotent.

- **Rotating `SECRET_KEY` logs everyone out.** Sessions use signed cookies, and the tracker derives
  deterministic session UUIDs from the key — changing it invalidates both.

- **First-boot health check.** `/health/` returns `503` until Postgres accepts connections. The
  config uses `healthcheckTimeout = 300` and `restartPolicyType = "ON_FAILURE"` to ride this out.
  This is a deployment check, not continuous proof of successful event collection.

## E. Daily maintenance (required)

Create a **new, separate cron service** from the same repository/revision as the web
service. Do not change the web service to a cron or clone its startup/bootstrap hooks.
Select `/railway.rollup.toml` as this service's config file. Railway config as code
is per-service and overrides dashboard values; the file does not provision a service.

Configure the job with a private reference to the same PostgreSQL service's
`DATABASE_URL`, `SECRET_KEY`, `DEBUG=False`, and `DJANGO_SETTINGS_MODULE=mantecato.settings`.
Use Railway secret/reference variables; never copy values into tracked files or logs.
No public domain, API key, admin password, Umami import configuration or HTTP health
check is needed. Verify there is **no pre-deploy migration/import** on this job;
the web release migrates once before the matching job revision is used.

The manifest runs:

```bash
uv run python manage.py run_daily_maintenance --rollup-runtime 900 --ai-runtime 120 --sql-timeout-ms 60000
```

Schedule: `15 2 * * *`, **02:15 UTC daily**, not local time. The job expires only
digests older than 396 days, then aggregates/deletes state for finished periods.
The current calendar month remains live. All pageview/event rows remain stored.
Per-site/period commits make interrupted runs resumable without adding counts twice.
Salts are deleted only after all day/scope state for their period has been finalized.

AI cleanup runs independently even if visitor rollup is busy or fails. It deletes
expired authentication records and audit older than 90 days in bounded batches;
JSON reports separate outcomes. It never changes analytics definitions or tracking.

The job exits and closes DB connections. `restartPolicyType=NEVER` avoids restart
loops. Railway skips a scheduled run if the preceding run is still active, so
alert on failures, incomplete/busy results, missing success for >24 h, and persistent
finished-period backlog. Cron timings are approximate; budget/SQL timeouts prevent
unbounded maintenance, not an absolute hard real-time deadline.

For controlled recovery after a backup and explicit authorization:

```bash
# Replace YYYY-MM with a finished calendar month before running.
uv run python manage.py rollup_visitors --period YYYY-MM --dry-run
uv run python manage.py rollup_visitors --period YYYY-MM --max-runtime 900
```

Replace the period with the actual finished period. `--website UUID` restricts the
site; retention follows the site selector but is independent of the period selector.
Dry-run performs no writes. JSON output distinguishes `completed`, `dry_run`,
`busy`, and `budget_exhausted`. Retention batches share the backfill lock: a busy
job preserves both backfill inputs and previously committed batch progress.
Incomplete runs exit 2; failures exit 1. Re-run
incomplete work in the job, never increase the web timeout to run it in requests.

For Render, containers or direct hosting, configure the same command in an external
daily cron with private DB access; web startup does not provide a fallback scheduler.
See [performance/recovery](PERFORMANCE.md) for rollout checks and benchmark limits.

## F. Optional remote AI connections

Remote MCP/OAuth is available when a valid `MANTECATO_PUBLIC_URL` is configured;
there is no separate enable flag. Leave the URL unset when unused. The matching
additive migrations create authentication/audit tables only. Before configuration,
restore-test backups, verify daily cleanup, HTTPS, host/CSRF validation and rollback. Gunicorn must see
an HTTPS MCP scope through the public proxy: configure the `FORWARDED_ALLOW_IPS`
environment variable with the actual trusted proxy addresses, consistently with
Django's proxy SSL header. Gunicorn 26 ASGI does not translate forwarded scheme
headers itself; Mantecato's MCP-only adapter does so for allowlisted peers only,
without changing collector/Django requests or client IPs. Do not accept arbitrary
forwarding headers on a directly exposed backend.
Gunicorn and the adapter read this directly from service Variables; `railway.toml`
does not provision those variables. Render's blueprint exposes it as an
operator-supplied value instead of hardcoding an unverified proxy network.

TLS terminates at the platform proxy, so its connection to Gunicorn may be HTTP.
Unless that peer is trusted, the adapter ignores `X-Forwarded-Proto: https` and
MCP sees `scope.scheme=http`. MCP then intentionally returns **404
`ai_access_unavailable`**, even if Django login/health work with
`USE_SECURE_PROXY_SSL_HEADER=True`. This is a conditional misconfiguration risk,
not proof that either platform's existing deployment is broken. See the
[public-proxy activation check](AI-CONNECTIONS.md#public-proxy-activation-check);
do not approve external client access until it passes. Do not use `FORWARDED_ALLOW_IPS=*` as an
unconditional workaround.

The manifest uses keep-alive 0 following isolated native-worker compatibility
tests. Test the chosen proxy and representative load rather than assuming a
production SLA. `/mcp` is stateless JSON-only Streamable HTTP, not legacy stdio.
Provider connections and cron creation require explicit operator actions; no
account-specific interoperability is implied. See [AI connections](AI-CONNECTIONS.md).
