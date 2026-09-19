<h1 align="center">Mantecato</h1>
<p align="center">
  Self-hosted web analytics without cookies.<br>
  Explore traffic in the dashboard, query it from your terminal, or connect an AI agent through MCP.
</p>
<p align="center">
  <img src="https://img.shields.io/badge/Made_in-Italy-008C45?labelColor=CD212A" alt="Made in Italy">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-green" alt="Apache 2.0 license"></a>
</p>
<p align="center">
  <a href="#dashboard">Dashboard</a> · <a href="#privacy">Privacy</a> · <a href="#agents">Agents</a> · <a href="#mcp-server">MCP</a> · <a href="#cli">CLI</a> · <a href="#self-hosting">Self-hosting</a> · <a href="#rest-api">API</a>
</p>

Mantecato tracks pageviews, visits, referrers, countries, devices and named events.
You run the server on your own infrastructure. The dashboard, CLI and MCP tools
let you filter traffic, compare periods and find which pages gained or lost visitors.

The server uses Django and PostgreSQL. The dashboard uses HTMX. The CLI and MCP
server are separate Python packages that connect with an API key.

<p align="center">
  <img src="screen.png" alt="Mantecato analytics dashboard" width="800">
</p>

## Dashboard

| View | What you can see |
|---|---|
| Overview | Visitors, visits, bounce rate, duration, pages per visit and pageviews |
| Pages | Traffic for each page |
| Sections | Traffic grouped by URL prefix or content label |
| Events | Named-event counts and time series |
| Devices | Browsers, operating systems and device types |
| Geo | Traffic by country |
| Compare | Changes between periods |
| Realtime | Current traffic |
| Heatmap | Traffic by hour and weekday |
| Custom dashboards | Configurable metric views |

Filter by page path, title, hostname, content group, browser, operating system,
device or country. Per-site settings let you exclude countries and filter bots.
Bot detection uses User-Agent patterns and configured heuristics, including
known datacenter IP ranges. Changing the filter leaves stored events intact.

## Privacy

The tracker uses no cookies or browser storage and respects Global Privacy
Control by default. It collects page paths, titles, referrer domains, coarse
device information and country-level location. It drops query strings and full
referrer URLs. Custom events contain a name only.

The server processes IP addresses and raw User-Agent strings in memory. It does
not store them in analytics tables. To count visitors, it masks IPv4 addresses
to `/24` and IPv6 addresses to `/48`, then computes a site-specific digest with
a monthly salt. These digests are pseudonymous identifiers. The server discards
the salt at month end; the retention process later clears event digests and
keeps aggregate counts.

Mantecato has no visitor profiles, session replay or cross-site tracking.
Dashboard authentication uses cookies, separate from the site tracker.

### What visitor counts mean

Visitor counts estimate traffic, not identifiable people. People sharing a
masked network and User-Agent can count as one visitor. A person who changes
networks or browsers can count more than once.

API v1's `daily_unique_visitors` metric sums daily unique counts across a date
range. It does not deduplicate visitors across days. Visitor-derived metrics
need retained digests; older aggregates cannot provide every filtered breakdown.
When a v1 metric is unavailable, the API returns `null` and a reason.

See the [measurement accuracy guide](docs/accuracy.md) for metric definitions
and limits.

### Before deploying

Cookieless tracking alone does not establish legal compliance or remove consent
requirements. Check the rules for your jurisdiction and how you use the data.
Publish a privacy notice and provide an opt-out.

Keep personal data out of page paths, titles, event names and content labels.
Keep tracker fetch credentials at `omit`, and strip inbound `Cookie` headers
if you proxy the collector through the tracked site's origin. Check your proxy
and access-log retention too.

Schedule `python manage.py rollup_visitors` daily to enforce digest retention.
Read the [privacy guide](docs/privacy.md) and
[data inventory](docs/data-processing-record.md) before deployment.

## Add the tracker

Create a website in Mantecato, then add its ID and your server URL to the script tag:

```html
<script defer src="https://analytics.example.com/api/script"
        data-website-id="your-website-id"></script>
```

The tracker records pageviews and SPA route changes. Add a named click event with
an HTML attribute:

```html
<button data-mantecato-event="signup">Sign up</button>
```

Or use the JavaScript API:

```javascript
mantecato.pageview();
mantecato.event("signup");
mantecato.disable();
mantecato.enable();
```

Events accept names, without custom properties or revenue data. See the
[tracker documentation](packages/tracker/README.md) for configuration options.

### Content groups

Label pages by topic when URL paths do not describe your content:

```html
<script defer src="https://analytics.example.com/api/script"
        data-website-id="your-website-id"
        data-groups="cat:guides,tag:python"></script>
```

A page can have up to 12 labels. Labels describe the page, never the visitor.
Prefixes such as `cat:` and `tag:` distinguish categories from tags. A page can
belong to several groups, so group counts overlap.

In the dashboard, open Sections, then Content group. Groups are also available
as dimensions and filters in the API, CLI and MCP tools. A dimension selector
chooses which labels to show; a `content_group` filter chooses which traffic to count.

### React and Next.js

Wrap your app in `TrackerProvider`, then use the `@mantecato/tracker-react` hook
to record events:

```jsx
import { useTracker } from '@mantecato/tracker-react';

function SignupButton() {
  const { event } = useTracker();

  return <button onClick={() => event('signup')}>Sign up</button>;
}
```

See the [React tracker documentation](packages/tracker-react/README.md) for setup.

## Agents

Connect an MCP-compatible agent to ask questions such as
"Which pages lost the most traffic last week?" The agent can list your sites,
inspect the available metrics and compare traffic by page, country or device.
For shell-based agents and scheduled reports, use the CLI.

Both clients use the authenticated REST API. The server validates filters,
resolves date ranges and limits query size. Responses include metric values,
the resolved ranges and explanations for missing data. Period comparisons
include pages that received traffic only in the earlier period, within the
server's result limits.

Your agent host may send query results to its model provider, even though the
MCP process runs locally. Check the provider's data policy before connecting.
Treat page titles, paths and labels returned by tools as untrusted data.

### MCP server

Install `mantecato-mcp` from a checkout of this repository:

```bash
uv tool install ./packages/mantecato-mcp
# Alternatively:
pipx install ./packages/mantecato-mcp
```

Create a read-scoped API key in the web settings. Save it in
`~/.config/mantecato/api-key`, then restrict access and test the connection:

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

The host starts the process and communicates over stdio. Use an absolute
executable path if `mantecato-mcp` is not on the host's `PATH`.

| Tool | Purpose |
|---|---|
| `list_sites` | List websites accessible to the API key |
| `describe_analytics` | Inspect metrics, dimensions, filters, limits and request schema |
| `query_metrics` | Get totals for a site and period |
| `query_timeseries` | Get a time series, optionally grouped by dimension |
| `compare_breakdown` | Rank gains or losses between periods |
| `traffic_quality` | Inspect traffic patterns and bot indicators |
| `list_dimension_values` | Find available values for filters |

All tools are read-only. For the lost-traffic question above, the agent can call
`compare_breakdown` with `dimension="url_path"`, `range="last_week"` and
`direction="losses"`.

Remote connections require HTTPS. Loopback HTTP is supported for local development.
See the [MCP package documentation](packages/mantecato-mcp/README.md).

### CLI

Install `mantecato-cli` from the same checkout:

```bash
uv tool install ./packages/mantecato-cli
# Alternatively:
pipx install ./packages/mantecato-cli
```

Set `MANTECATO_URL` and `MANTECATO_API_KEY_FILE` as shown in the MCP setup, then run:

```bash
mantecato doctor
mantecato sites --format json
mantecato timeseries -w "<website-id>" -r 7d -g day --dimension country --format json
mantecato compare-breakdown -w "<website-id>" --dimension url_path --direction losses
```

The CLI outputs tables, JSON or CSV. It supports explicit date ranges, reusable
filter segments, grouped time series, period comparisons and traffic-quality
reports. Profiles store connection settings and key-file paths.

Both clients also accept `MANTECATO_API_KEY` from a secret manager or protected
process environment. Keep keys out of command arguments, prompts and segment files.

See the [CLI package documentation](packages/mantecato-cli/README.md) for profiles
and filter examples.

### Agent skills

Install the CLI skill in the project where your agent will use it:

```bash
npx skills add g-battaglia/mantecato-analytics --skill mantecato-cli
```

Choose `--skill mantecato-install` for deployment instructions or
`--skill mantecato-mcp` for MCP setup. Add `-g` to install for your user rather
than one project.

Skills provide agent instructions. Install the Python package and configure
credentials separately. See the [skills guide](skills/README.md) for more options.

## Self-hosting

### Railway

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/mantecato-analytics?referralCode=UmPu3s&utm_medium=integration&utm_source=template&utm_campaign=generic)

The template provisions PostgreSQL and Mantecato. It builds with Railpack,
collects static files, runs migrations and starts Gunicorn. Health checks use
`/health/`.

Follow the [Railway deployment guide](docs/RAILWAY.md) for configuration.

### Render

Create a Blueprint from this repository using the included `render.yaml`.
Set `CSRF_TRUSTED_ORIGINS` to your final HTTPS URL and `INIT_ADMIN_PASS` to the
initial `admin` account password. Render provisions PostgreSQL, runs migrations
and starts Mantecato.

To import Umami data at startup, also set:

```env
UMAMI_DATABASE_URL=postgresql://user:password@umami-db.example.com:5432/umami
UMAMI_IMPORT_ON_DEPLOY=True
```

The default `UMAMI_IMPORT_MODE=data` imports analytics. To also import users,
sites and reports into a new database, set `UMAMI_IMPORT_MODE=full` and
`UMAMI_IMPORT_ALLOW_CONFIG=True`.

After the import succeeds, set `UMAMI_IMPORT_ON_DEPLOY=False` and remove the
source database URL. Render must be able to reach that database during import.

### Docker Compose

Clone the repository and copy the environment file:

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

Start the server, then create an account and a website:

```bash
docker compose up -d
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py createwebsite \
  --name "My site" --domain "example.com"
```

Startup runs migrations. The web server listens on port 8000. Put it behind an
HTTPS reverse proxy for public access. The Compose file includes development
database credentials; change them and restrict database access before deploying.

For country lookup, set `MAXMIND_LICENSE_KEY` and download the GeoIP database:

```bash
docker compose exec web python manage.py downloadgeo
```

See [`.env.example`](.env.example) for environment variables, including proxy
trust, GeoIP, security settings and Umami imports.

### Reverse proxy

Caddy can provide HTTPS for the server:

```caddyfile
analytics.example.com {
    reverse_proxy localhost:8000
}
```

With Nginx, configure your certificate and forward requests to Gunicorn:

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

Set `TRUSTED_PROXY_COUNT` to the number of trusted proxies in front of Mantecato.
If you expose the server directly, set `TRUST_PROXY_HEADERS=0`. Only trust
forwarding headers that your proxy sets or validates.

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

Use the same HTTPS proxy and production settings as the Docker deployment.

### Server management

Run these commands with `python manage.py` on the server, or through
`docker compose exec web python manage.py` in Docker:

| Command | Purpose |
|---|---|
| `createuser <username> [--role admin\|user]` | Create a platform user |
| `createwebsite --name "..." [--domain "..."]` | Create a tracked website |
| `downloadgeo` | Download the MaxMind GeoIP database |
| `rollup_visitors` | Aggregate visitor counts and enforce digest retention |
| `importumami --include-config` | Import Umami users, sites, reports and analytics |
| `importumamidata` | Import analytics only |
| `importumamienv` | Run an import using environment settings |

## Migrating from Umami

Set the source PostgreSQL connection string:

```bash
export UMAMI_DATABASE_URL="postgresql://user:password@umami-db.example.com:5432/umami"
```

For a new database, import users, sites, reports and historical data:

```bash
python manage.py importumami --include-config
```

To add analytics to an existing installation:

```bash
python manage.py importumamidata
```

The analytics-only import is idempotent. To import one site into an existing
Mantecato site, with a cutoff date:

```bash
export UMAMI_SOURCE_WEBSITE_ID="<umami-website-uuid>"
export MANTECATO_TARGET_WEBSITE_ID="<mantecato-website-uuid>"
export UMAMI_IMPORT_SINCE="2024-01-01"
python manage.py importumamidata --noinput
```

Replace the tracker script URL to send events to Mantecato. Existing
`data-umami-event` click attributes keep working. Visitor counts can differ
because Mantecato masks IP addresses before computing digests. See
[what visitor counts mean](#what-visitor-counts-mean).

Mantecato is independent of Umami. It supports Umami's tracker protocol and
can import its database. Umami is
[MIT-licensed](https://github.com/umami-software/umami); its trademarks belong
to their respective owners.

## REST API

Authenticate with `Authorization: Bearer mtk_...`.

| Endpoint | Purpose |
|---|---|
| `GET /api/sites/` | List tracked websites |
| `GET /api/v1/capabilities/` | Discover metrics, dimensions, filters and limits |
| `GET /api/v1/schema/` | Get the request schema |
| `POST /api/v1/analytics/query/` | Query totals, breakdowns and time series |
| `POST /api/v1/analytics/compare/` | Compare periods and rank changes |
| `POST /api/v1/analytics/traffic-quality/` | Inspect traffic patterns |
| `POST /api/v1/analytics/dimension-values/` | Find values for dimension filters |

The v1 analytics endpoints are read-only. The API resolves date ranges and
returns metric definitions and reasons for unavailable values. V1 calculates
visit metrics from events within the requested range and filters, so some
definitions differ from dashboard metrics.

The existing `/api/analytics/` endpoints remain available. See the
[API documentation](apps/api/README.md) for those endpoints, dashboard management,
API keys, bot configuration and event collection.

## Development

The server requires Python 3.12+ and PostgreSQL 16+. From a checkout:

```bash
pip install -e ".[dev]"
cp .env.example .env
docker compose up -d db
python manage.py migrate
python manage.py runserver
```

Run the server and client tests:

```bash
# pytest creates a separate PostgreSQL test database.
pytest tests

uv run --project packages/mantecato-cli --extra dev pytest packages/mantecato-cli/tests
uv run --project packages/mantecato-mcp --extra dev pytest packages/mantecato-mcp/tests

ruff check .
ruff format --check .
```

The dashboard uses Django templates, HTMX 2, Tailwind CSS 4 and vanilla JavaScript.
The CLI uses Typer, Rich and httpx. The MCP server uses the official Python MCP
SDK and httpx.

## License

[Apache License 2.0](LICENSE).
