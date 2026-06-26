<p align="center">
  <img src="https://img.shields.io/badge/Django-6.x-092E20?logo=django&logoColor=white" alt="Django 6">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/HTMX-2.x-3366CC?logo=htmx&logoColor=white" alt="HTMX">
  <img src="https://img.shields.io/badge/PostgreSQL-16+-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Tailwind_CSS-4-06B6D4?logo=tailwindcss&logoColor=white" alt="Tailwind CSS">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License">
</p>

<h1 align="center">📊 Mantecato</h1>

<p align="center">
  <strong>The ethical web analytics platform — for agents and humans.</strong><br>
  Cookieless aggregate analytics. No analytics consent banners. No third-party tracking.<br>
  Self-hosted, privacy-first, AI-native — built with Django + HTMX.
</p>

<p align="center">
  <em>On a mission to become the best self-hosted analytics — privacy by design, not by checkbox.</em>
</p>

<p align="center">
  <a href="#-self-hosting">🏠 Self-Host</a> · <a href="#-dashboard">🖥️ Dashboard</a> · <a href="#-cli">💻 CLI</a> · <a href="#-rest-api">🔌 API</a> · <a href="#-mcp-server">🤖 MCP</a> · <a href="#-migrating-from-umami">🔄 From Umami</a>
</p>

<p align="center">
  <img src="screen.png" alt="Mantecato Dashboard" width="800">
</p>

### 🚂 Deploy on Railway

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/mantecato-analytics?referralCode=UmPu3s&utm_medium=integration&utm_source=template&utm_campaign=generic)

One click provisions PostgreSQL 16 + Mantecato, wired together automatically.
The bundled `railway.toml` (Railpack builder) runs migrations in a pre-deploy
step, collects static files at build time, and serves the app with gunicorn on
Railway's injected `$PORT`. Health checks hit `/health/`.

See [docs/RAILWAY.md](docs/RAILWAY.md) for the full environment-variable
reference and for publishing your own copy of the community template.

---

## ✨ Why Mantecato?

Most analytics tools are built for humans clicking around a dashboard. Mantecato is built for that **and** for AI agents that need to query, analyze, and act on your data programmatically.

Every metric available in the dashboard is also available through the CLI, the REST API, the Python SDK, and the MCP server. AI agents are first-class citizens — they get the same data, the same filters, the same granularity as a human browsing the UI.

| | |
|---|---|
| 🔒 **Privacy-first** | Cookieless, no browser storage, no persistent or cross-site identifier, no third-party tracking — runs without a consent banner |
| 🎯 **Exact, not estimated** | Exact daily unique visitors, visits and bounce rate via a compute-and-discard scheme — no cookies, no stored identifier ([how](docs/privacy.md)) |
| 🪶 **Lightweight tracker** | ~2 KB JavaScript — your site stays fast, your Lighthouse score stays high |
| 🏠 **Self-hosted** | Your analytics infrastructure can run on your own server. Hosted or third-party deployments may require appropriate agreements |
| ⚡ **Real-time** | See aggregate pageviews happening right now and which pages are active |
| 📈 **Analytics views** | Overview, pages, sections, events, devices, geo maps, compare, heatmap, custom dashboards |
| 🤖 **AI-native** | MCP server, REST API, Python SDK, CLI with JSON output — every interface an agent needs to work autonomously |
| 💻 **CLI** | Query everything from the terminal — output in table, JSON, or CSV |
| 🔌 **Full REST API** | 25+ endpoints with API key auth — integrate analytics into any workflow |
| 🐍 **Python SDK** | `mantecato-client` — access everything programmatically from scripts and notebooks |
| 🕵️ **Bot detection** | Built-in heuristics to filter out crawlers, scrapers, and automated traffic |
| 🔄 **Umami-compatible** | Same wire protocol — drop-in replacement with one-command data import |

---

## 🚀 How It Works

Add one script tag to your site:

```html
<script defer src="https://your-mantecato.com/api/script"
        data-website-id="your-website-id"></script>
```

That's it. Aggregate pageview data starts flowing into your dashboard instantly. No build step, no npm install, no configuration files.

Want to track custom events?

```html
<!-- 🎯 Track clicks with HTML attributes -->
<button data-mantecato-event="signup">Sign Up</button>
```

Custom events record an **event name only**. By design there is no event
payload, no revenue tracking, and no visitor identification — Mantecato is
cookieless and aggregate, so there is nothing to attach a person to.

The tracker automatically handles SPA route changes, **respects Global Privacy
Control (GPC) by default** (the legacy Do Not Track header is opt-in), and can be
toggled on and off by visitors.

For maximum measurement accuracy on a self-hosted, first-party deployment — count
privacy opt-outs and dodge ad-blockers via first-party proxying — see
[docs/accuracy.md](docs/accuracy.md).

---

## 🔒 Privacy & Compliance

Mantecato is built to run **without a cookie/consent banner** and to fit the major
privacy regimes **by construction**. _Engineering-for-compliance, not legal advice —
have counsel confirm for your specific deployment._

**Why there's no banner.** The banner trigger (ePrivacy **Art. 5(3)** / UK PECR) is
about *storing or accessing information on the device*. Mantecato uses **no cookies
and no browser storage** (`credentials: "omit"`), so it never does that — regardless
of anything done server-side.

**Optimised for GDPR and the consent-exempt audience-measurement frameworks.** The
privacy-critical parameters are **fixed and non-configurable**, so the posture cannot
be misconfigured:

- **first-party / single-site** — no cross-site or cross-day tracking, no fingerprinting
- client **IP masked to `/24` (IPv4) · `/48` (IPv6)** and **never stored** (used transiently, then discarded)
- short-lived **in-month identifier** (random monthly salt, deleted at month end), **≤ 13 months**, no per-visit renewal
- **country-level geo only** (no region/city), **aggregate-only output**
- **Global Privacy Control (GPC) honoured** by default

| Region | Framework | Status |
|---|---|---|
| 🇪🇺 EU | GDPR + ePrivacy | **No banner** (no device storage); transient IP/UA on the consent-exempt audience-measurement basis |
| 🇮🇹 Italy | **Garante** — cookie guidelines (2021) | Met: IP masked on ≥ 4th octet, single-site, aggregate-only |
| 🇫🇷 France | **CNIL** — *Sheet n°16* | Met: last IP octet dropped (`/24`), ≤ 13-month identifier, ≤ 25-month retention |
| 🇬🇧 UK | PECR + DUAA 2025 (statistical purposes) | No banner; first-party, transparency + opt-out |
| 🇺🇸 US | CCPA/CPRA + state laws | No sale/share, no cross-context ads, **GPC honoured** → privacy-policy disclosure only |
| 🇨🇦 / 🇦🇺 | PIPEDA · Québec Law 25 / Privacy Act (APPs) | No banner; transparency notice, no sensitive data |

Details: [docs/privacy.md](docs/privacy.md) (legal basis, model privacy notice) ·
[docs/data-processing-record.md](docs/data-processing-record.md) (authority-ready data inventory).

### 📉 Accuracy trade-off: visitor counts are deliberately conservative

Because the IP is **masked to `/24` and never stored**, Mantecato cannot distinguish
visitors who share the same network block **and** the same browser — it counts them
as **one** visitor. As a result, **unique-visitor counts read lower than full-IP tools**
(Google Analytics, Umami, …); the gap **grows with the time range** and is **largest on
desktop / shared networks** (offices, ISPs, campuses, mobile CGNAT). This is the
privacy ↔ precision trade-off — **by design, not a bug**:

- **Pageviews, visits and trends are unaffected** — only the *distinct-visitor* figure is conservative.
- That masking is exactly what keeps the no-banner, consent-exempt posture valid; recovering those visitors would require the **full IP**, which steps outside the EU audience-measurement exemption.
- It is the "cookieless ceiling" every cookieless tool has — Mantecato simply errs on the side of privacy. More in [docs/accuracy.md](docs/accuracy.md).

---

## 🖥️ Dashboard

A full-featured, responsive analytics dashboard with interactive charts and maps. No JavaScript framework — just fast, server-rendered pages with HTMX for instant interactivity.

| | |
|---|---|
| 📋 **Overview** | Exact visitors, visits, bounce rate, avg. duration, pages/visit and pageviews at a glance, with tabs for quick drill-downs |
| 📄 **Pages** | Top pages by views |
| 📂 **Sections** | Hierarchical URL grouping — see how `/blog/`, `/docs/`, `/pricing/` perform as a whole |
| 🎯 **Events** | Custom event breakdown (event name + counts) and time series |
| 📱 **Devices** | Browsers, operating systems, device types |
| 🌍 **Geo** | Interactive world map at **country level only** (no region/city, to avoid re-identification) |
| ⚖️ **Compare** | Period-over-period comparison (previous period or previous year) with % change |
| ⚡ **Realtime** | Live aggregate pageview count and current pages |
| 🗓️ **Heatmap** | Traffic heatmap by hour of day × day of week |
| 🎨 **Custom Dashboards** | Build your own views with the metrics that matter to you |

> Unique visitors are exact **per day**; over a multi-day range the figure is the
> sum of daily uniques. Returning-visitor / cross-day metrics, sessions lists,
> journeys, funnels, retention and revenue are intentionally **not** offered —
> they require a persistent identifier. See [docs/privacy.md](docs/privacy.md).

### 🔍 Filtering

Every analytics view supports filtering on the dimensions actually stored:

| Filter | Examples |
|---|---|
| **Content** | `url_path`, `page_title`, `hostname`, `event_name` |
| **Devices** | `browser`, `os`, `device` |
| **Geo** | `country` |

Operators: `eq`, `neq`, `contains`, `not_contains`, `starts_with`, `not_starts_with`.

> Note: visitor/visit/bounce KPIs are shown without a content/device/geo filter
> active; with such a filter they read `N/A` (exact counts come from aggregate
> tables that cannot be sliced by those dimensions).

### 🤖 Bot Detection

Built-in heuristics to keep your data clean:

- 🕷️ **User-agent matching** — detects Googlebot, Bingbot, Yandex, Baidu, Selenium, Puppeteer, and 30+ known crawler patterns
- 🫥 **Empty user-agent** — flags requests with no User-Agent
- 🌍 **Country exclusion** — optionally drop traffic from selected countries

Configurable per website — toggle each heuristic on or off from the settings page.

---

## 💻 CLI

Query your analytics from the terminal. Every command supports `--format table|json|csv`, making it easy to pipe data into scripts, notebooks, or dashboards.

```bash
mantecato overview -w <website-id> -r 7d --format table
mantecato top-pages -w <website-id> --filter country:IT --format json
mantecato events -w <website-id> -r today --format csv > events.csv
```

### 📊 Analytics Commands

High-level commands that mirror the dashboard views:

| Command | Description |
|---|---|
| `overview` | Site-wide overview metrics (exact visitors, visits, bounce, duration) |
| `pages` | Page-level analytics with pagination |
| `events` | Custom event breakdown |
| `devices` | Browser, OS, device type |
| `geo` | Country-level geographic breakdown |
| `compare` | Period-over-period comparison |
| `realtime` | Live aggregate pageview data |

### 🔎 Query Commands

Low-level access to the query engine — more granular, more flexible:

| Command | Description |
|---|---|
| `stats` | Raw overview stats with derived metrics |
| `timeseries` | Pageview and visits time series |
| `top-pages` | Top pages ranked by views (path or title mode) |
| `top-sections` | Hierarchical URL section analysis |
| `event-timeseries` | Time series for a single event |
| `filter-values` | Available filter values for a column |
| `heatmap` | Traffic heatmap by hour/day |

### 🛠️ CRUD Commands

Manage resources from the terminal:

| Command | Description |
|---|---|
| `sites` | List tracked websites |
| `dashboards` / `dashboard` | List or get custom dashboards |
| `dashboard-create` / `dashboard-delete` | Create or delete a dashboard |
| `api-keys` / `api-key-create` / `api-key-delete` | Manage API keys |
| `scheduled-exports` / `scheduled-export-delete` | Manage scheduled exports |
| `bot-config` | View bot detection configuration |

### ⚙️ Common Options

| Option | Description |
|---|---|
| `-w`, `--website` | Website UUID |
| `-r`, `--range` | Date range preset (`today`, `7d`, `30d`, `90d`, `12mo`, etc.) |
| `-l`, `--limit` | Number of results (default: 20) |
| `--filter` | Repeatable filter (`column:operator:value`) |
| `--format` | Output format: `table`, `json`, `csv` |
| `-g`, `--granularity` | Time bucket: `minute`, `hour`, `day`, `week`, `month` |

---

## 🔌 REST API

All analytics data is available via a JSON REST API. Authenticate with API keys (`Authorization: Bearer mtk_...`).

### 📊 Analytics Endpoints

All `GET` requests. Pass `website` (UUID), `start_at`, `end_at`, and optional `filter` parameters.

| Endpoint | Description |
|---|---|
| `GET /api/analytics/overview/` | Aggregated site-wide metrics (exact visitors/visits/bounce) |
| `GET /api/analytics/pages/` | Page-level analytics (paginated) |
| `GET /api/analytics/events/` | Custom event analytics |
| `GET /api/analytics/devices/` | Device/browser/OS breakdowns |
| `GET /api/analytics/geo/` | Country-level geographic breakdown |
| `GET /api/analytics/compare/` | Period comparison |
| `GET /api/analytics/realtime/` | Live aggregate pageview activity |

### 🛠️ Management Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/sites/` | List tracked websites |
| `GET/POST /api/dashboards/` | List / create dashboards |
| `GET/POST /api/dashboards/<id>/` | Get / update / delete a dashboard |
| `GET/POST /api/api-keys/` | List / create API keys |
| `POST /api/api-keys/<id>/delete/` | Revoke an API key |
| `GET/POST /api/bot-config/` | Get / save bot detection config |

### 📡 Tracker Endpoints

| Endpoint | Description |
|---|---|
| `POST /api/send` | Event ingestion (Umami-compatible wire protocol) |
| `GET /api/script` | Serve the JavaScript tracker bundle |

---

## 🤖 MCP Server — AI Agents as First-Class Citizens

Mantecato ships with a built-in [MCP](https://modelcontextprotocol.io/) server exposing **41 tools**. This means any MCP-compatible AI assistant — Claude, Cursor, Windsurf, Claude Code, custom agents — can query, analyze, and manage your analytics data directly, without writing code or calling APIs.

This isn't a wrapper around the dashboard. It's the same query engine, the same filters, the same data — just surfaced through a protocol that AI agents speak natively.

**What an agent can do:**

| | |
|---|---|
| 📊 **Query** | "Show me top pages for the last 7 days, filtered by country:IT" |
| 📈 **Compare** | "How did visits and bounce rate change compared to last month?" |
| 🎯 **Events** | "Which custom events fired most this week?" |
| 🌍 **Geo analysis** | "Break down pageviews by country for Q1" |
| 📱 **Devices** | "What's the browser and OS split for `/pricing`?" |
| 🛠️ **Manage** | "Create a new dashboard tracking weekly KPIs for the marketing team" |
| ⚡ **Realtime** | "How many aggregate pageviews are happening right now and on which pages?" |

**Why this matters:**

Traditional analytics tools require a human to open a browser, navigate to the right page, set the right filters, and interpret the charts. With Mantecato's MCP server, an AI agent can do all of that in a single conversation turn — and chain multiple queries together to answer complex questions that would take a human several clicks and tab switches.

Build autonomous workflows: an agent that monitors traffic drops and alerts you, a weekly report generator that highlights anomalies, a content strategy assistant that correlates page performance with traffic sources — all powered by the same data as your dashboard.

---

## 📦 Packages

### 🟨 @mantecato/tracker

Lightweight JavaScript tracker (~2 KB minified). Cookie-free, Umami-compatible.

```html
<script defer src="https://your-mantecato.com/api/script"
        data-website-id="your-website-id"></script>
```

**Features:**
- ✅ Automatic pageview tracking
- ✅ SPA route change detection
- ✅ Custom event tracking (event **name only** — no event properties)
- ✅ Click tracking via `data-mantecato-event` attributes (with `data-umami-event` fallback)
- ✅ Global Privacy Control (GPC) respected **by default** (legacy DNT opt-in)
- ✅ Client-side bot filtering
- ✅ CORS-enabled for cross-origin tracking
- ✅ No cookies, no `localStorage`/`sessionStorage`, no fingerprinting

> Not supported by design (cookieless, aggregate): revenue tracking, visitor
> identification, and event properties/payloads.

**JavaScript API:**

```javascript
// 📄 Track a pageview
mantecato.pageview();

// 🎯 Track a custom event (name only)
mantecato.event("signup");

// ⏸️ Toggle tracking
mantecato.disable();
mantecato.enable();
```

### ⚛️ @mantecato/tracker-react

React/Next.js hooks for pageview and event tracking:

```jsx
import { useTracker } from '@mantecato/tracker-react';

function App() {
  const { track } = useTracker();

  return (
    <button onClick={() => track('signup')}>
      Sign Up
    </button>
  );
}
```

### 🐍 mantecato-client (Python SDK)

Full-featured Python SDK built on httpx. Access every API endpoint programmatically.

```python
from mantecato_client import MantecatoClient

with MantecatoClient("https://analytics.example.com", api_key="mtk_xxx") as client:
    # 📊 Analytics
    overview = client.analytics.overview(site_id, date_range="30d")
    pages = client.analytics.pages(site_id, date_range="7d", page=1)
    geo = client.analytics.geo(site_id, date_range="30d", country="IT")
    compare = client.analytics.compare(site_id, date_range="30d")
    realtime = client.analytics.realtime(site_id)

    # 🌐 Sites
    sites = client.sites.list()

    # 🎨 Dashboards
    dashboards = client.dashboards.list(website_id=site_id)
    client.dashboards.create(name="Weekly KPIs", website_id=site_id, config={...})

    # 🔑 API Keys
    keys = client.api_keys.list()
    new_key = client.api_keys.create(name="CI pipeline")

    # 🤖 Bot Config
    config = client.bot_config.get(website_id=site_id)
```

---

## 🏠 Self-Hosting

### ☁️ Deploy on Render

The included `render.yaml` is a self-contained Blueprint. Its `repo` field is
intentionally omitted, so Render deploys the repository that contains the
Blueprint directly; no fork or repository URL edit is required.

1. In Render, create a new Blueprint from this repository.
2. Set `CSRF_TRUSTED_ORIGINS` to the final HTTPS URL.
3. Set `INIT_ADMIN_PASS` to create the initial `admin` account.
4. Deploy. Render provisions a private PostgreSQL database, runs migrations,
   and starts Mantecato. This also works on Render's free web service plan.

To import an existing Umami database during Render startup, set:

```env
UMAMI_DATABASE_URL=postgresql://user:password@umami-db.example.com:5432/umami
UMAMI_IMPORT_ON_DEPLOY=True
```

The default `UMAMI_IMPORT_MODE=data` imports analytics only and is idempotent.
For a new Mantecato database that also needs Umami users, websites and reports,
explicitly set:

```env
UMAMI_IMPORT_MODE=full
UMAMI_IMPORT_ALLOW_CONFIG=True
```

After the import succeeds, set `UMAMI_IMPORT_ON_DEPLOY=False` and remove
`UMAMI_DATABASE_URL` from Render unless it is needed again. The Umami database
must be reachable from Render.

### 🐳 With Docker (recommended)

The fastest way to get Mantecato running. You need [Docker](https://docs.docker.com/get-docker/) and Docker Compose.

**1. Clone and configure**

```bash
git clone https://github.com/your-org/mantecato.git
cd mantecato
cp .env.example .env
```

**2. Edit `.env`**

Set at least these values:

| Variable | Description |
|---|---|
| `SECRET_KEY` | 🔑 A random string, 50+ chars. Generate with `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `DEBUG` | Set to `False` for production |
| `ALLOWED_HOSTS` | Your domain, e.g. `analytics.example.com` |
| `CSRF_TRUSTED_ORIGINS` | Full URL, e.g. `https://analytics.example.com` |

<details>
<summary>📋 Full list of environment variables</summary>

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | — | Django secret key (required) |
| `DEBUG` | `True` | Debug mode |
| `DATABASE_URL` | — | PostgreSQL connection string |
| `ALLOWED_HOSTS` | — | Comma-separated list of allowed hostnames |
| `PRODUCTION_HOSTS` | — | Hosts that trigger production security settings |
| `CSRF_TRUSTED_ORIGINS` | — | Comma-separated HTTPS origins for CSRF |
| `SECURE_SSL_REDIRECT` | `True` | Redirect HTTP to HTTPS |
| `SESSION_COOKIE_SECURE` | `True` | Secure flag on session cookies |
| `CSRF_COOKIE_SECURE` | `True` | Secure flag on CSRF cookies |
| `SECURE_HSTS_SECONDS` | `31536000` | HSTS header duration (1 year) |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `True` | Include subdomains in HSTS |
| `SECURE_HSTS_PRELOAD` | `False` | HSTS preload flag |
| `USE_SECURE_PROXY_SSL_HEADER` | `True` | Trust `X-Forwarded-Proto` header |
| `MAXMIND_LICENSE_KEY` | — | MaxMind license key for GeoIP |
| `GEO_DATABASE_URL` | — | Custom GeoIP database URL |
| `GEOIP_PATH` | `./geo/GeoLite2-City.mmdb` | Path to GeoIP database file |
| `CLIENT_IP_HEADER` | — | Custom IP header (e.g. `CF-Connecting-IP`) |
| `SENTRY_DSN` | — | Sentry DSN for error tracking |
| `LANGUAGE_CODE` | `en-us` | Default language |
| `TIME_ZONE` | `UTC` | Server time zone |
| `UMAMI_DATABASE_URL` | — | Source Umami PostgreSQL connection string |
| `UMAMI_IMPORT_ON_DEPLOY` | `False` | Run an idempotent Umami import during deploy |
| `UMAMI_IMPORT_MODE` | `data` | `data` for analytics only, or `full` for configuration too |
| `UMAMI_IMPORT_ALLOW_CONFIG` | `False` | Required acknowledgement for `full` imports |
| `UMAMI_SOURCE_WEBSITE_ID` | — | Optional source site UUID for a data-only import |
| `MANTECATO_TARGET_WEBSITE_ID` | — | Optional destination site UUID for a data-only import |
| `UMAMI_IMPORT_SINCE` | — | Optional analytics cutoff date in `YYYY-MM-DD` format |

</details>

**3. Start everything**

```bash
docker compose up -d
```

This starts two containers:
- 🐘 **PostgreSQL 16** — database with persistent volume
- 🌐 **Mantecato** — web server with Gunicorn

The database schema is created automatically on first boot. Health checks are built in.

**4. Create admin + first website**

```bash
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py createwebsite \
  --name "My Site" --domain "example.com"
```

**5. (Optional) Enable geolocation 🌍**

```bash
docker compose exec web python manage.py downloadgeo
```

Requires a free [MaxMind license key](https://www.maxmind.com/en/geolite2/signup) — set `MAXMIND_LICENSE_KEY` in `.env`.

**6. Open the dashboard** — visit `http://localhost:8000` and log in 🎉

### 🔐 Reverse Proxy (production)

For HTTPS, put Mantecato behind a reverse proxy. Here are examples for the most common options:

<details>
<summary>🔷 Caddy (automatic HTTPS)</summary>

```
analytics.example.com {
    reverse_proxy localhost:8000
}
```

That's it — Caddy handles SSL certificates automatically.

</details>

<details>
<summary>🟩 Nginx</summary>

```nginx
server {
    listen 443 ssl http2;
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

</details>

Make sure your `.env` has the production security settings enabled (they are by default when `DEBUG=False`).

If your proxy sets a custom IP header (e.g. Cloudflare's `CF-Connecting-IP`), configure it:

```env
CLIENT_IP_HEADER=CF-Connecting-IP
```

### 🐍 Without Docker

If you prefer to run Mantecato directly on your machine:

```bash
# 📦 Install dependencies
pip install -e .

# 🗃️ Set up the database
python manage.py migrate

# 👤 Create admin user
python manage.py createsuperuser

# 🌐 Create a website to track
python manage.py createwebsite --name "My Site" --domain "example.com"

# 🌍 (Optional) Download GeoIP database
python manage.py downloadgeo

# 📁 Collect static files (production only)
python manage.py collectstatic --noinput

# 🚀 Start the server
gunicorn mantecato.wsgi:application --bind 0.0.0.0:8000 --workers 3
```

Requires Python 3.12+ and PostgreSQL 16+.

### ⚙️ Management Commands

| Command | Description |
|---|---|
| `createuser <username> [--role admin\|user]` | 👤 Create a platform user |
| `createwebsite --name "..." [--domain "..."]` | 🌐 Create a tracked website |
| `downloadgeo` | 🌍 Download the MaxMind GeoLite2 database |
| `importumami [--source-db <dsn>] --include-config` | 🔄 Full import from an Umami PostgreSQL database |
| `importumamidata [--source-db <dsn>]` | 📥 Import analytics data only |
| `importumamienv` | ☁️ Run the optional environment-configured deploy import |

### 💾 System Requirements

| | Minimum | Recommended |
|---|---|---|
| **CPU** | 1 core | 2+ cores |
| **RAM** | 512 MB | 1 GB+ |
| **Disk** | 1 GB | 10 GB+ (depends on traffic) |
| **PostgreSQL** | 16 | 16+ |
| **Python** | 3.12 | 3.12+ |

Runs comfortably on a small VPS — a $5/month server handles tens of thousands of pageviews per day.

### 🔧 Tuning

| Variable | Default | Description |
|---|---|---|
| `GUNICORN_WORKERS` | 3 | Number of Gunicorn worker processes |
| `GUNICORN_TIMEOUT` | 60 | Request timeout in seconds |

Rule of thumb: set workers to `(2 × CPU cores) + 1`.

---

## 🔄 Migrating from Umami

Already using Umami? Mantecato can import your existing data.

Set the source PostgreSQL connection string once:

```bash
export UMAMI_DATABASE_URL="postgresql://user:password@umami-db.example.com:5432/umami"
```

**Full import** into a new database (users, sites, reports and historical data):

```bash
python manage.py importumami --include-config
```

**Data only** (safe, additive and idempotent):

```bash
python manage.py importumamidata
```

For a single site, map an Umami site onto an existing Mantecato site:

```bash
export UMAMI_SOURCE_WEBSITE_ID="<umami-website-uuid>"
export MANTECATO_TARGET_WEBSITE_ID="<mantecato-website-uuid>"
export UMAMI_IMPORT_SINCE="2024-01-01"
python manage.py importumamidata --noinput
```

Your existing `data-umami-event` HTML attributes keep working — the tracker is wire-compatible. Just swap the script URL and you're done.

> **Heads-up on the numbers:** for its consent-exempt privacy posture Mantecato masks
> the IP to `/24`, whereas Umami hashes the full IP. So after migrating, **unique-visitor
> counts read somewhat lower than Umami** (most on desktop / shared networks; the gap
> grows with the date range) — **pageviews and trends stay comparable**. This is by
> design — see [Privacy & Compliance](#-privacy--compliance).

> **Mantecato is an independent project — not affiliated with or endorsed by Umami.** It is a from-scratch Django implementation that speaks Umami's tracker wire protocol and can import an Umami database, so you can migrate without re-instrumenting your sites. Umami is [MIT-licensed](https://github.com/umami-software/umami) and a trademark of its respective owners.

---

## 🏗️ Architecture

```
                   ┌───────────────────┐
                   │   Browser / App   │
                   └────────┬──────────┘
                            │
              POST /api/send (JS tracker)
                            │
                            ▼
┌──────────────────┐   ┌────────┐   ┌──────────────────┐
│  Web Dashboard   │   │        │   │   CLI / MCP /     │
│  (HTMX + Django  │◄─►│   DB   │◄─►│   Python SDK     │
│   templates)     │   │  (Pg)  │   │                  │
└──────────────────┘   └────────┘   └──────────────────┘
                            ▲
                            │
                     Query Engine
                   (raw SQL, 3000+ lines)
```

- The **JS tracker** sends events to `POST /api/send` (Umami-compatible wire protocol)
- The **web dashboard** reads data through the query engine and renders it with HTMX
- The **CLI** and **MCP server** access the same data via the query engine (local) or JSON API (remote)
- The **Python SDK** uses the JSON API over HTTP
- The **query engine** is 3000+ lines of optimized raw SQL — CTEs, window functions, `PERCENTILE_CONT`, and more

---

## 🛠️ Tech Stack

| | |
|---|---|
| 🐍 **Backend** | Django 6, Python 3.12+ |
| 🐘 **Database** | PostgreSQL 16+ |
| ⚡ **Frontend** | HTMX 2, Tailwind CSS 4, vanilla JS |
| 📊 **Charts** | Chart.js, Leaflet (maps), d3-sankey (Sankey diagrams) |
| 💻 **CLI** | Typer + Rich + Textual |
| 📡 **Tracker** | ~2 KB, cookie-free, Umami-compatible |
| 🐍 **Python SDK** | httpx-based, async-ready |
| 🌍 **GeoIP** | MaxMind GeoLite2-City |
| ⚙️ **Tasks** | Management commands + cron |

No JavaScript framework. No task queue. No Redis. No build step.

---

## 🧑‍💻 Development

```bash
# 📦 Install with dev dependencies
pip install -e ".[dev]"

# 🗃️ Set up database
cp .env.example .env
python manage.py migrate

# 🚀 Run the dev server
python manage.py runserver

# ✅ Run tests
pytest

# 🧹 Lint and format
ruff check .
ruff format .
```

---

## 📄 License

MIT — do whatever you want with it.
