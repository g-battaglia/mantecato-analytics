<h1 align="center">Mantecato</h1>
<p align="center">
  <strong>Privacy-first, agentic-first web analytics.</strong><br>
  Self-hosted analytics with native MCP tools, an independent CLI, and a web dashboard.<br>
  Agents query aggregate analytics through the API, not the database.
</p>
<p align="center">
  <img src="https://img.shields.io/badge/Privacy-first-008C45" alt="Privacy first">
  <img src="https://img.shields.io/badge/Agentic-first-0057B8" alt="Agentic first">
  <img src="https://img.shields.io/badge/Made_in-Italy-008C45?labelColor=CD212A" alt="Made in Italy">
  <img src="https://img.shields.io/badge/License-Apache_2.0-green" alt="Apache 2.0 license">
</p>
<p align="center">
  <a href="#privacy-first">Privacy</a> · <a href="#agentic-first">Agents</a> · <a href="#mcp-server">MCP</a> · <a href="#cli">CLI</a> · <a href="#dashboard">Dashboard</a> · <a href="#self-hosting">Self-hosting</a> · <a href="#rest-api">API</a>
</p>

Mantecato measures website traffic without cookies or browser storage. It runs on
Django and PostgreSQL, with a server-rendered HTMX dashboard. You host the analytics
server and choose who can query it.

**Agent access is a first-class, native interface.** The repository includes
`mantecato-mcp` for MCP-compatible agents and `mantecato-cli` for terminal workflows
and automation. Both call the authenticated REST API. Neither needs Django,
database credentials, a browser session, or dashboard scraping.

<p align="center">
  <img src="screen.png" alt="Mantecato analytics dashboard" width="800">
</p>

## Privacy first

The default tracker uses no cookies, localStorage, or sessionStorage. It respects
Global Privacy Control by default. Collection keeps page paths, referrer domains,
coarse device information and country-level location, not full referrer URLs or
precise location. Custom events contain a name, not a user-defined payload.

IP addresses and raw User-Agent strings are processed transiently, not stored in
the analytics tables. Before computing visitor digests, the server masks IPv4
addresses to `/24` and IPv6 addresses to `/48`. Digests use a site-specific input
and a monthly salt. Retained digests are pseudonymous identifiers. The server
discards the salt at month end; the retention process later clears event digests
while preserving aggregate counts.

There are no visitor profiles, session replay, or cross-site tracking. Operators
must keep personal data out of page paths, titles, event names and content-group
labels. Schedule `rollup_visitors` to enforce digest retention, and check that
proxy and access logs follow your privacy policy too.

### Consent and deployment responsibilities

The default cookieless tracker is designed for consent-exempt audience measurement.
That is not a blanket compliance guarantee. Your jurisdiction, proxy configuration,
other scripts and use of the data determine the obligations for your deployment.
Mantecato does not make unrelated tracking consent-free.

Keep tracker fetch credentials at `omit`. For a same-origin collector proxy, strip
inbound `Cookie` headers. Publish a privacy notice, retain an opt-out, and confirm
your lawful basis and consent requirements before deployment.

See [privacy and data facts](docs/privacy.md), the
[field-by-field data inventory](docs/data-processing-record.md), and the
[measurement accuracy guide](docs/accuracy.md).

### What visitor counts mean

Cookieless counts are not counts of identifiable people. Browsers that share a
masked network and the same User-Agent can merge; changes in network or browser
can split one person's activity. These effects can also change derived visit
metrics.

API v1 names its visitor metric `daily_unique_visitors`. Across several days, it
sums daily unique counts rather than claiming a count of distinct people for the
whole period. When retained visitor keys are unavailable, affected v1 metrics are
`null` with an explanation rather than zero.

## Agentic first

An agent can discover accessible sites and supported metrics, query a time series,
and compare periods through native MCP tools. The CLI offers the same versioned
analytics API for shell-based agents and scheduled jobs. The web dashboard remains
available for interactive analysis.

The repository ships [agent skills](skills/README.md) for CLI analytics,
installation and MCP setup. They contain instructions, not wrappers, and use the
installed Python packages directly. Install the CLI skill from the development
branch in your project with:

```bash
npx skills add https://github.com/g-battaglia/mantecato-analytics/tree/develop --skill mantecato-cli
```

Use `--skill mantecato-install` for deployment guidance or `--skill mantecato-mcp`
for MCP configuration. Add `-g` to install for your user instead of one project.
Installing a skill does not install the application or configure its credentials.
See the [skills guide](skills/README.md) for local-checkout installation and the
shorter command available after these skills reach the default branch.

The server resolves date ranges, validates filters and enforces query limits.
Responses include numeric metrics, range metadata and reasons for unavailable
values. Comparisons include dimensions that disappeared in the current period,
subject to the server's cardinality limit.

For example, an agent can answer "Which pages lost the most traffic last week?"
by calling `list_sites`, inspecting `describe_analytics`, and using
`compare_breakdown` with `dimension="url_path"`, `range="last_week"` and
`direction="losses"`. It does not need to generate SQL or read the dashboard.

MCP tools are read-only. Give the MCP process a read-scoped API key through its
protected environment or a key file. The key is not a tool argument. Remote
connections require HTTPS; HTTP is allowed only on loopback for development.

**Connecting an external agent changes where query results go.** The MCP process
runs locally, but its host may send returned analytics to a model provider. Choose
your agent and provider policy accordingly. Treat page titles, paths and labels in
tool results as untrusted data, not instructions.

### MCP server

`mantecato-mcp` is an independent stdio server built with the official Python MCP
SDK. It calls the REST API directly, without invoking the CLI. Its tools are:

| Tool | Purpose |
|---|---|
| `list_sites` | List websites accessible to the API key |
| `describe_analytics` | Discover metrics, dimensions, filters, limits and the request schema |
| `query_metrics` | Read aggregate metrics for a site and period |
| `query_timeseries` | Read a time series, optionally grouped by dimensions |
| `compare_breakdown` | Rank gains or losses between periods |
| `traffic_quality` | Inspect measured traffic patterns without changing bot labels |
| `list_dimension_values` | Discover bounded dimension values for filters |

The client packages are in this repository and are not yet published to PyPI.
From a checkout, install the MCP package with:

```bash
uv tool install ./packages/mantecato-mcp
# Or: pipx install ./packages/mantecato-mcp
```

Create a read-scoped API key in the web settings. Save it in a file readable only
by your user, then configure the connection:

```bash
chmod 600 "$HOME/.config/mantecato/api-key"
export MANTECATO_URL="https://analytics.example.com"
export MANTECATO_API_KEY_FILE="$HOME/.config/mantecato/api-key"
mantecato-mcp --check
```

For an MCP host that accepts `mcpServers` configuration:

```json
{
  "mcpServers": {
    "mantecato": {
      "command": "mantecato-mcp",
      "env": {
        "MANTECATO_URL": "https://analytics.example.com",
        "MANTECATO_API_KEY_FILE": "/absolute/path/to/private/api-key"
      }
    }
  }
}
```

Use an absolute executable path if the host cannot find `mantecato-mcp` on its
`PATH`. The host starts the stdio process. No HTTP MCP listener or public MCP port
is required. There are no administrative tools or unrestricted SQL tools.

See the [MCP package documentation](packages/mantecato-mcp/README.md).

### CLI

`mantecato-cli` is a separate HTTP client with table, JSON and CSV output. From a
checkout:

```bash
uv tool install ./packages/mantecato-cli
# Or: pipx install ./packages/mantecato-cli
```

It uses the same `MANTECATO_URL` and `MANTECATO_API_KEY_FILE` variables as the MCP
server. A secret manager can instead supply `MANTECATO_API_KEY` in the process
environment. Do not put the key in command arguments, shell history, prompts, or
segment files.

```bash
mantecato doctor
mantecato sites --format json
mantecato timeseries -w <website-id> -r 7d -g day --dimension country --format json
mantecato compare-breakdown -w <website-id> --dimension url_path --direction losses
```

The CLI supports explicit half-open date ranges, reusable filter segments,
dimensional time series, comparisons and traffic-quality diagnostics. Profiles
store connection settings and key-file paths, not inline keys.

See the [CLI package documentation](packages/mantecato-cli/README.md).

## Add the tracker

Add a script tag to your site:

```html
<script defer src="https://your-mantecato.com/api/script"
        data-website-id="your-website-id"></script>
```

The tracker records pageviews and handles SPA route changes. To record a named
click event:

```html
<button data-mantecato-event="signup">Sign up</button>
```

Custom events carry a name only. There are no event properties, revenue payloads
or visitor identification calls.

### Content groups

Use site-declared labels when URL paths do not describe your content:

```html
<script defer src="https://your-mantecato.com/api/script"
        data-website-id="your-website-id"
        data-groups="cat:guides,tag:python"></script>
```

A page can have up to 12 labels. Labels describe the page, never the visitor.
Prefixes such as `cat:` and `tag:` separate taxonomies. Because one page can belong
to several groups, group counts overlap and must not be added as a site total.

Find groups in the dashboard under Sections, then Content group. They are also
available through API v1, CLI and MCP dimensions and filters. A dimension selector
narrows the labels shown; a `content_group` filter scopes the underlying traffic.

## Dashboard

The dashboard uses server-rendered Django templates and HTMX, without a frontend
application framework.

| View | Data |
|---|---|
| Overview | Visitors, visits, bounce rate, duration, pages per visit and pageviews |
| Pages | Page-level traffic |
| Sections | URL-prefix groups and content groups |
| Events | Named-event counts and time series |
| Devices | Browsers, operating systems and device types |
| Geo | Country-level map, without city or region data |
| Compare | Period comparisons with percentage changes |
| Realtime | Current aggregate traffic |
| Heatmap | Traffic by hour and weekday |
| Custom dashboards | Configurable metric views |

### Filtering and bot detection

Analytics views support stored dimensions such as page path, title, hostname,
content group, browser, operating system, device and country. Visitor-derived
metrics depend on retained keys; older anonymous aggregates cannot supply every
dimensional breakdown.

Bot detection uses known User-Agent patterns and other configured heuristics.
Per-site settings control the read-time bot filter and country exclusions. API v1
traffic-quality indicators describe measured patterns; they do not rewrite the
stored bot classification.

## REST API

Clients authenticate with `Authorization: Bearer mtk_...`. API v1 is additive;
the existing endpoints remain available.

### Versioned analytics

| Endpoint | Description |
|---|---|
| `GET /api/v1/capabilities/` | Metrics, dimensions, filters and server limits |
| `GET /api/v1/schema/` | Request schema discovery |
| `POST /api/v1/analytics/query/` | Totals, breakdowns and time series |
| `POST /api/v1/analytics/compare/` | Period comparisons and ranked changes |
| `POST /api/v1/analytics/traffic-quality/` | Behavioral diagnostics |
| `POST /api/v1/analytics/dimension-values/` | Bounded dimension discovery |

The analytics POST endpoints query data; they do not modify it. API key
validation may update the key's last-used timestamp. Analytics SQL runs in a
read-only transaction with statement and lock timeouts.

V1 derives visit metrics from events within the requested range and filters.
Do not assume every metric has the same definition as a dashboard metric. Read
the metric metadata and unavailable-value explanations returned by the API.

### Existing analytics endpoints

These GET endpoints accept `website`, `start_at`, `end_at` and optional `filter`
parameters:

| Endpoint | Description |
|---|---|
| `/api/analytics/overview/` | Site-wide metrics |
| `/api/analytics/pages/` | Paginated page analytics |
| `/api/analytics/events/` | Custom-event analytics |
| `/api/analytics/devices/` | Device, browser and OS breakdowns |
| `/api/analytics/geo/` | Country breakdown |
| `/api/analytics/compare/` | Period comparison |
| `/api/analytics/realtime/` | Current aggregate activity |

### Management and collection

| Endpoint | Description |
|---|---|
| `GET /api/sites/` | List tracked websites |
| `GET/POST /api/dashboards/` | List or create dashboards |
| `GET/POST /api/dashboards/<id>/` | Read or manage a dashboard |
| `GET/POST /api/api-keys/` | List or create API keys |
| `POST /api/api-keys/<id>/delete/` | Revoke an API key |
| `GET/POST /api/bot-config/` | Read or save bot configuration |
| `POST /api/send` | Collect events using the Umami-compatible wire protocol |
| `GET /api/script` | Serve the tracker bundle |

See the [API documentation](apps/api/README.md). The former Python SDK is retired;
custom integrations can call the REST API directly.

## Tracker packages

### `@mantecato/tracker`

The JavaScript tracker supports automatic pageviews, SPA navigation, named events,
content groups and click attributes. It respects GPC by default; legacy Do Not
Track support is opt-in. It does not use cookies or browser storage.

```javascript
mantecato.pageview();
mantecato.event("signup");
mantecato.disable();
mantecato.enable();
```

### `@mantecato/tracker-react`

React and Next.js applications can use the tracker hook:

```jsx
import { useTracker } from '@mantecato/tracker-react';

function App() {
  const { track } = useTracker();

  return <button onClick={() => track('signup')}>Sign up</button>;
}
```

## Self-hosting

### Deploy on Railway

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/mantecato-analytics?referralCode=UmPu3s&utm_medium=integration&utm_source=template&utm_campaign=generic)

The template provisions PostgreSQL and Mantecato. The included `railway.toml`
uses Railpack, runs migrations before deployment, collects static files at build
time and serves Gunicorn on Railway's `$PORT`. Health checks use `/health/`.

See the [Railway deployment guide](docs/RAILWAY.md).

### Deploy on Render

The included `render.yaml` is a Blueprint that deploys the repository containing
it. No repository URL edit is needed.

1. Create a new Blueprint from this repository.
2. Set `CSRF_TRUSTED_ORIGINS` to the final HTTPS URL.
3. Set `INIT_ADMIN_PASS` to create the initial `admin` account.
4. Deploy. Render provisions PostgreSQL, runs migrations and starts Mantecato.

To import Umami data during startup, set:

```env
UMAMI_DATABASE_URL=postgresql://user:password@umami-db.example.com:5432/umami
UMAMI_IMPORT_ON_DEPLOY=True
```

The default `UMAMI_IMPORT_MODE=data` imports analytics only and is idempotent.
For a new database that also needs users, sites and reports, set
`UMAMI_IMPORT_MODE=full` and `UMAMI_IMPORT_ALLOW_CONFIG=True`.

After a successful import, set `UMAMI_IMPORT_ON_DEPLOY=False` and remove
`UMAMI_DATABASE_URL` unless another import needs it. Render must be able to reach
the source database.

### Docker Compose

Install Docker and Docker Compose, then clone and configure the server:

```bash
git clone https://github.com/g-battaglia/mantecato-analytics.git
cd mantecato-analytics
cp .env.example .env
```

Set `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` in
`.env`. Generate a secret with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Start PostgreSQL and the web server, then create an account and a website:

```bash
docker compose up -d
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py createwebsite \
  --name "My site" --domain "example.com"
```

Startup runs migrations. Open `http://localhost:8000` for local development;
use HTTPS and the production settings for a public deployment.

For country lookup, set `MAXMIND_LICENSE_KEY` and download the GeoIP database:

```bash
docker compose exec web python manage.py downloadgeo
```

<details>
<summary>Environment variables</summary>

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | Required | Django secret key |
| `DEBUG` | `True` | Set to `False` in production |
| `DATABASE_URL` | Required | PostgreSQL connection string |
| `ALLOWED_HOSTS` | Configure | Comma-separated allowed hostnames |
| `PRODUCTION_HOSTS` | Unset | Hosts that trigger production security settings |
| `CSRF_TRUSTED_ORIGINS` | Configure | Comma-separated HTTPS origins |
| `SECURE_SSL_REDIRECT` | `True` | Redirect HTTP to HTTPS |
| `SESSION_COOKIE_SECURE` | `True` | Secure flag on dashboard session cookies |
| `CSRF_COOKIE_SECURE` | `True` | Secure flag on dashboard CSRF cookies |
| `SECURE_HSTS_SECONDS` | `31536000` | HSTS duration in seconds |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `True` | Include subdomains in HSTS |
| `SECURE_HSTS_PRELOAD` | `False` | HSTS preload flag |
| `USE_SECURE_PROXY_SSL_HEADER` | `True` | Trust `X-Forwarded-Proto` |
| `MAXMIND_LICENSE_KEY` | Unset | MaxMind license key |
| `GEO_DATABASE_URL` | Unset | Custom GeoIP database URL |
| `GEOIP_PATH` | `./geo/GeoLite2-City.mmdb` | GeoIP database path |
| `CLIENT_IP_HEADER` | Unset | Custom IP header, such as `CF-Connecting-IP` |
| `SENTRY_DSN` | Unset | Optional error reporting |
| `LANGUAGE_CODE` | `en-us` | Default language |
| `TIME_ZONE` | `UTC` | Server time zone |
| `UMAMI_DATABASE_URL` | Unset | Source Umami PostgreSQL connection string |
| `UMAMI_IMPORT_ON_DEPLOY` | `False` | Import during deployment |
| `UMAMI_IMPORT_MODE` | `data` | Analytics only, or `full` for configuration too |
| `UMAMI_IMPORT_ALLOW_CONFIG` | `False` | Required acknowledgement for full imports |
| `UMAMI_SOURCE_WEBSITE_ID` | Unset | Source site for a data-only import |
| `MANTECATO_TARGET_WEBSITE_ID` | Unset | Destination site for a data-only import |
| `UMAMI_IMPORT_SINCE` | Unset | Import cutoff date in `YYYY-MM-DD` format |

Dashboard login cookies are separate from the cookieless site tracker.

</details>

### Reverse proxy

For example, Caddy can terminate HTTPS:

```caddyfile
analytics.example.com {
    reverse_proxy localhost:8000
}
```

With Nginx, configure your certificate and forward the request to Gunicorn:

```nginx
server {
    listen 443 ssl;
    server_name analytics.example.com;

    ssl_certificate     /etc/letsencrypt/live/analytics.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/analytics.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 80;
    server_name analytics.example.com;
    return 301 https://$host$request_uri;
}
```

Configure trusted proxy handling for your deployment. Do not trust client-supplied
forwarding headers without checking the proxy chain. If your proxy provides a
custom client-IP header, set `CLIENT_IP_HEADER` to that header.

### Without Docker

Use Python 3.12+ and PostgreSQL 16+. Configure `.env`, then run:

```bash
pip install -e .
python manage.py migrate
python manage.py createsuperuser
python manage.py createwebsite --name "My site" --domain "example.com"
python manage.py collectstatic --noinput
gunicorn mantecato.wsgi:application --bind 0.0.0.0:8000 --workers 3
```

### Management commands

| Command | Purpose |
|---|---|
| `createuser <username> [--role admin\|user]` | Create a platform user |
| `createwebsite --name "..." [--domain "..."]` | Create a tracked website |
| `downloadgeo` | Download the MaxMind GeoIP database |
| `rollup_visitors` | Roll up visitor aggregates and enforce digest retention |
| `importumami --include-config` | Import Umami users, sites, reports and analytics |
| `importumamidata` | Import analytics only |
| `importumamienv` | Run the environment-configured deployment import |

Run these on the server with `python manage.py`. They are separate from the remote
`mantecato` CLI.

### Resources and tuning

PostgreSQL 16+ and Python 3.12+ are required. Size memory and disk for your traffic,
retention and query workload. `GUNICORN_WORKERS` defaults to `3` and
`GUNICORN_TIMEOUT` to `60` seconds. Measure resource use before increasing workers.

## Migrating from Umami

Set the source PostgreSQL connection string:

```bash
export UMAMI_DATABASE_URL="postgresql://user:password@umami-db.example.com:5432/umami"
```

For a new database, import users, sites, reports and historical data:

```bash
python manage.py importumami --include-config
```

For an additive, idempotent analytics-only import:

```bash
python manage.py importumamidata
```

To map a single source site to an existing Mantecato site:

```bash
export UMAMI_SOURCE_WEBSITE_ID="<umami-website-uuid>"
export MANTECATO_TARGET_WEBSITE_ID="<mantecato-website-uuid>"
export UMAMI_IMPORT_SINCE="2024-01-01"
python manage.py importumamidata --noinput
```

Existing `data-umami-event` click attributes keep working. Replace the tracker
script URL to send events to Mantecato. Visitor counts can differ because
Mantecato masks IP addresses before computing digests. See
[what visitor counts mean](#what-visitor-counts-mean).

Mantecato is an independent project, not affiliated with or endorsed by Umami.
It implements Umami's tracker wire protocol and can import an Umami database.
Umami is [MIT-licensed](https://github.com/umami-software/umami); its trademarks
belong to their respective owners.

## Architecture

```text
Browser tracker -> POST /api/send -> Django -> PostgreSQL
Web dashboard   -> Django views and query engine -> PostgreSQL
Remote CLI      -> HTTPS and API key -> Django REST API
Agent host      -> local MCP over stdio -> HTTPS and API key -> Django REST API
```

The server owns collection and analytics queries. CLI and MCP are independent
Python packages with private HTTP adapters. Neither package depends on the other
or accesses PostgreSQL. API v1 adds analytics operations without changing tracker
payloads or existing dashboard routes.

| Component | Technology |
|---|---|
| Server | Django 6, Python 3.12+ |
| Database | PostgreSQL 16+ |
| Dashboard | HTMX 2, Tailwind CSS 4, vanilla JavaScript |
| CLI | Typer, Rich, httpx |
| MCP | Official Python MCP SDK, stdio, httpx |
| GeoIP | Local MaxMind database |
| Scheduled work | Management commands and cron |

## Development

```bash
pip install -e ".[dev]"
cp .env.example .env

# PostgreSQL is the only supported database backend.
docker compose up -d db
python manage.py migrate
python manage.py runserver

# pytest creates an isolated PostgreSQL test database.
pytest tests

# Independent client tests.
uv run --project packages/mantecato-cli --extra dev pytest packages/mantecato-cli/tests
uv run --project packages/mantecato-mcp --extra dev pytest packages/mantecato-mcp/tests

ruff check .
ruff format .
```

## License

[Apache License 2.0](LICENSE). You can use, modify and distribute Mantecato under
its terms, including the attribution and NOTICE requirements and patent grant.
