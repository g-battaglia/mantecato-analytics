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
- **Start** — gunicorn serves `mantecato.wsgi:application` on Railway's injected `$PORT`.
- **Health check** — Railway probes `/health/`, which runs `SELECT 1` against PostgreSQL.

> **Heads up — config as code only covers one service.** Unlike `render.yaml`, a Railway
> `railway.toml` describes *only the build and deploy of a single service*. It does **not** provision
> the database or the environment variables. Those live on the Railway side (dashboard / CLI) and,
> for a reusable template, are baked into the template itself (see below).

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
| `USE_SECURE_PROXY_SSL_HEADER` | `True` | ✅ | Railway terminates TLS upstream. Without this, `SECURE_SSL_REDIRECT` causes an HTTPS redirect loop. |
| `RAILPACK_PYTHON_VERSION` | `3.12` | ⚙️ | Pins the Python version. Railpack otherwise defaults to 3.13.x. |
| `GUNICORN_WORKERS` | `2` | – | Worker processes (tune to your plan's RAM). |
| `GUNICORN_TIMEOUT` | `120` | – | Worker timeout in seconds. |
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
