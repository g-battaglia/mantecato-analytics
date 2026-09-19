---
name: mantecato-install
description: Install, configure or upgrade a self-hosted Mantecato analytics server and its independent CLI or MCP clients. Use for first-time setup, deployment preparation, tracker integration and post-deploy checks. Distinguish server installation from connecting a client to an existing server.
license: Apache-2.0
compatibility: Server setup requires PostgreSQL 16+ and Python 3.12+ or a supported container platform. Client installation requires Python 3.12+ and uv or pipx. Deployment requires operator authorization.
---

# Install Mantecato

First establish what the user needs. A running Mantecato server, a local CLI and a
local MCP process are separate installations. Installing a skill supplies agent
instructions, not any of those applications.

If the user already has a server and wants to query it, install only the requested
client. Do not provision PostgreSQL, deploy another server, or modify the website.
For a new server, confirm the target host, domain, deployment method and database.
Before upgrading, confirm the deployed version, backup and rollback procedure.
Do not deploy, migrate, create accounts or change a live tracker without permission.

## Obtain the application

Use a trusted checkout of `https://github.com/g-battaglia/mantecato-analytics`.
Select an operator-approved revision. The new client packages and API v1 are on
`develop`; the default branch may not contain them yet. Do not overwrite an existing
checkout or discard local changes. To obtain this development version:

```bash
git clone --branch develop https://github.com/g-battaglia/mantecato-analytics.git
cd mantecato-analytics
```

For production, use the approved release or commit rather than assuming that a
moving development branch is a stable release.

This skill can be installed without the application source. File names below refer
to the application checkout, not the directory containing this skill. Resolve its
absolute path before running commands. Read that checkout's `README.md`,
`.env.example` and chosen deployment manifest because release requirements can change.

## Install a client for an existing server

The independent clients do not install Django or connect to PostgreSQL. They need
the server's HTTPS URL and an API key, not database credentials. The client packages
are not yet published to PyPI; install the requested one from the trusted checkout:

```bash
uv tool install /absolute/path/to/mantecato-analytics/packages/mantecato-cli
```

```bash
uv tool install /absolute/path/to/mantecato-analytics/packages/mantecato-mcp
```

Use `pipx install` with the same path if the user prefers pipx. Do not install both
clients unless needed. Check `mantecato --version` or `mantecato-mcp --version`.
After a source update, reinstall the chosen package with `uv tool install --force`.

The operator creates a read-scoped API key in the server's web settings. Have them
save it to a private file outside version control. Never ask them to paste it into
the conversation, print it, or put it in a command argument. On Unix the file must
be readable only by its owner, typically mode `600`.

Configure the client process with the actual approved URL and absolute key-file
path, replacing these examples:

```bash
export MANTECATO_URL="https://analytics.example.com"
export MANTECATO_API_KEY_FILE="/absolute/path/to/private/api-key"
```

A secret manager can supply `MANTECATO_API_KEY` instead. It takes precedence over
the file. Do not dump process environments to troubleshoot credentials.

For the CLI, run `mantecato doctor --format json`. For MCP, run
`mantecato-mcp --check`. A version or help response proves installation only; a
successful authenticated check proves connection to the server and API v1.
If authentication fails, stop and ask the operator to correct the credential.
If v1 is missing, the server needs the corresponding release, not a database bypass.

## Prepare a new server

The server requires PostgreSQL 16+ and Python 3.12+. SQLite is not supported.
Keep the database private and use dedicated credentials. Read existing configuration
without exposing secrets; create a local `.env` from `.env.example` only if no
configuration exists. Do not overwrite a deployed environment with example values.

For public deployments, configure:

| Setting | Requirement |
|---|---|
| `SECRET_KEY` | A generated secret stored outside version control |
| `DATABASE_URL` | The intended PostgreSQL database, only on the server |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | Explicit server hostnames, not `*` |
| `CSRF_TRUSTED_ORIGINS` | The dashboard's HTTPS origins |
| HTTPS and cookies | Keep production redirect and secure-cookie protections |
| Proxy trust | Match forwarding-header trust to the actual proxy chain |

Do not reuse example database passwords. Do not put secrets in generated commands
or logs. If temporary bootstrap credentials are used, arrange password rotation
and removal from deployment configuration afterward.

### Choose the deployment method

For Railway, use the checkout's `railway.toml` and `docs/RAILWAY.md`. Its pipeline
collects static files, applies migrations and starts Gunicorn on the platform port.
For Render, use `render.yaml`. Supply the requested secrets and trusted origins;
review the template's host settings before exposing it publicly.

For containers, use `Dockerfile.standalone` with the operator's database and secret
configuration. Its startup runs migrations and static collection. The bundled
`docker-compose.yml` contains example database credentials and publishes port 5432.
It is not a hardened production deployment. Require a reviewed override or deployment
configuration before public use. Do not run `docker compose down -v` or replace an
existing database volume as part of an upgrade.

For a direct Python installation, run the following in the application checkout
only after confirming the database and authorizing migrations:

```bash
uv sync
uv run python manage.py check
uv run python manage.py migrate --noinput
uv run python manage.py collectstatic --noinput
```

Configure Gunicorn through the host's process manager. Use `manage.py runserver`
only for local development. Do not expose a development server as production.

Before any production upgrade, verify a restorable database backup and the rollback
limits of migrations. Never treat a health check as proof that rollback is safe.
Do not import Umami data, purge analytics or change retention during an ordinary
installation unless the user separately requests it.

## Create the site and connect its tracker

Create the initial account through the approved deployment bootstrap or the
interactive `manage.py createsuperuser` command. Do not invent or publish a default
password. Create the tracked website in the dashboard under its intended owner.
If using `manage.py createwebsite`, specify the intended `--user-id`; an unowned
site will not be accessible to an ordinary user's read-scoped API key.

For a site that is not already instrumented, replace the host and UUID with the
server and website just created:

```html
<script defer src="https://analytics.example.com/api/script"
        data-website-id="website-uuid"></script>
```

The website UUID is public. The API key is not and must never appear in HTML,
frontend environment variables, tracker attributes or browser requests. Inspect
the existing layout first to avoid loading two trackers. If the tracker already
points to this server, a CLI/MCP upgrade does not require replacing it.

Keep Global Privacy Control support enabled and fetch credentials at `omit`.
Review same-origin proxies so they do not forward cookies to collection. Do not
remove consent controls needed by other services on the site. Keep personal data
out of paths, titles, event names and content-group labels.

## Verify and hand over

Check `/health/`, the dashboard login and the expected site's access permissions.
After an authorized test pageview, confirm collection reaches the intended site.
Schedule `manage.py rollup_visitors` for retention enforcement. Configure country
lookup with `manage.py downloadgeo` only if GeoIP is wanted and credentials are set.

Validate the installed client with `mantecato doctor --format json` or
`mantecato-mcp --check`, then read one bounded query. Do not broaden key scopes
merely to hide a site-ownership error. Keep API keys and database credentials out
of the handover report.

Report the deployed revision, URL, verification results and remaining operator
steps. State explicitly if the server is only configured, not deployed, or if
live authentication or collection remains unverified. Installation instructions
do not authorize publishing packages, pushing commits or deploying other projects.
