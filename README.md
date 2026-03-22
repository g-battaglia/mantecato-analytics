# Mantecato

Standalone analytics dashboard that reads from a shared Umami PostgreSQL database. Built with Next.js 16, it provides a comprehensive web UI, a full-featured CLI, and an MCP server for AI agent integration.

## Stack

- **Next.js 16** (Turbopack) + React 19
- **PostgreSQL** (Neon) via Prisma 7.5 with client engine
- **shadcn/ui** + Radix for UI components
- **Recharts** for charts, **react-simple-maps** for world map
- **TanStack Query** for data fetching, **TanStack Table** for data tables
- **Commander.js** for CLI, **@modelcontextprotocol/sdk** for MCP server

## Setup

```bash
# Install dependencies (--legacy-peer-deps needed for react-simple-maps)
npm install --legacy-peer-deps

# Create .env with your Neon database URL
echo 'DATABASE_URL="postgresql://..."' > .env
echo 'SESSION_SECRET="your-secret"' >> .env

# Pull the Prisma schema from the database (read-only, never migrate)
npx prisma db pull

# Generate Prisma client
npx prisma generate

# Start the dev server (port 3001 by default)
npm run dev -- -p 3001
```

### Docker

Run the full stack via Docker (compatible with Docker Desktop, Apple Containers, and Podman):

```bash
# Build and start the web dashboard
docker compose up web --build

# Or use the CLI / MCP server as one-off containers
docker compose run --rm cli stats --site kerykeion.net --period 30d
docker compose run --rm mcp
```

See [docs/docker.md](docs/docker.md) for multi-arch builds, Apple Containers tips, and production configuration.

## Web Dashboard

15+ analytics pages covering:

| Page | Description |
|------|-------------|
| **Overview** | Pageviews, visitors, visits, bounce rate, avg duration, pages/visit with time series |
| **Pages** | Page analytics with views, time-on-page, entries/exits, bounce rate + page detail drill-down |
| **Sources** | Referrers, UTM params, channels, click IDs, hostnames + referrer page drill-down |
| **Events** | Custom event metrics with time series and property breakdown |
| **Sessions** | Session list with full event replay timeline |
| **Devices** | Browser, OS, device type, screen size, language breakdown with donut charts |
| **Geo** | Country/region/city breakdown with world map choropleth |
| **Realtime** | Live active visitors and recent events |
| **Compare** | Current vs previous period comparison |
| **Retention** | Cohort retention analysis |
| **Funnels** | Multi-step funnel analysis with conversion rates |
| **Journeys** | User journey paths with Sankey diagram |
| **Revenue** | Revenue analytics (summary, time series, by event/country) |
| **Engagement** | Duration distribution, percentiles, bounce rates |
| **Dashboards** | Custom widget dashboards with drag-and-drop |
| **Settings** | Site management and configuration |

Additional features: saved views, annotations, scheduled exports, public share links, PDF/PNG export, table virtualization for large datasets, advanced filter system with OR logic.

---

## Authentication

The web dashboard uses session-based JWT auth (login with username/password).

The CLI and MCP server use **API keys** for authentication. Keys are generated from the web UI and required for CRUD commands (annotations, saved views, dashboards, scheduled exports). Read-only analytics commands work without auth.

```bash
# Generate a key: Settings > API Keys > New Key (in the web UI)

# Use via environment variable (recommended)
export MANTECATO_API_KEY="mtk_..."

# Or pass directly
mantecato annotations --site kerykeion.net --api-key "mtk_..."
```

Key format: `mtk_<base64url-random>`. Only the SHA-256 hash is stored — the raw key is shown once at creation. See [docs/authentication.md](docs/authentication.md) for details.

---

## CLI

Full analytics access from the terminal. Every metric available in the web UI can be queried via CLI.

### Quick Start

```bash
# Set your API key (required for CRUD commands)
export MANTECATO_API_KEY="mtk_..."

# Via npm script
npm run cli -- stats --site kerykeion.net --period 30d

# Via npx
npx tsx src/cli/index.ts stats --site kerykeion.net --period 30d
```

> Full command reference with all 38 commands: [docs/cli.md](docs/cli.md)

### Global Options

Every analytics command supports these options:

| Option | Description | Default |
|--------|-------------|---------|
| `-s, --site <site>` | Site name, domain, or UUID | required |
| `-p, --period <preset>` | Date preset: `7d`, `30d`, `90d`, `this_month`, `last_month`, etc. | `30d` |
| `--start <date>` | Custom start date (ISO 8601) | - |
| `--end <date>` | Custom end date (ISO 8601) | - |
| `-f, --format <format>` | Output: `json`, `table`, `csv` | `table` |
| `--filter <filter...>` | Filters as `column:operator:value` (repeatable) | - |
| `-l, --limit <n>` | Max rows | `20` |
| `-g, --granularity <g>` | `auto`, `minute`, `hour`, `day`, `week`, `month` | `auto` |

**Site resolution** is flexible. All of these work:
```bash
--site kerykeion.net           # by name
--site www.kerykeion.net       # by full domain
--site b52bd153-29af-...       # by UUID
--site kery                    # by partial name match
```

### Commands Reference

#### Core Analytics

```bash
# List all tracked sites
mantecato sites

# Overview stats
mantecato stats --site kerykeion.net --period 30d

# Time series (pageviews + visitors over time)
mantecato timeseries --site kerykeion.net --period 7d --granularity hour

# Compare current vs previous period
mantecato compare --site kerykeion.net --period 30d
```

#### Pages

```bash
# Page analytics (views, time-on-page, bounce rate, entries/exits)
mantecato pages --site kerykeion.net --period 30d --limit 10

# Page detail (referrers, next pages, time distribution, time series)
mantecato page-detail --site kerykeion.net --url /content/docs --period 30d

# Quick top pages
mantecato top-pages --site kerykeion.net --period 7d --limit 5
```

#### Sources

```bash
# Traffic sources with bounce rate and duration
mantecato sources --site kerykeion.net --period 30d

# Referrer drill-down (which pages a referrer drives traffic to)
mantecato referrer-pages --site kerykeion.net --referrer google.com --period 30d

# Auto-grouped traffic channels
mantecato channels --site kerykeion.net --period 30d

# UTM parameter breakdown
mantecato utm --site kerykeion.net --period 30d

# Click ID analysis (gclid, fbclid, etc.)
mantecato clickids --site kerykeion.net --period 30d

# Hostname breakdown
mantecato hostnames --site kerykeion.net --period 30d

# Quick top referrers
mantecato top-referrers --site kerykeion.net --period 30d --limit 5
```

#### Events

```bash
# Custom event metrics
mantecato events --site kerykeion.net --period 30d

# Event detail (time series + property breakdown)
mantecato event-detail --site kerykeion.net --event transit_fetch_success --period 30d

# Quick top events
mantecato top-events --site kerykeion.net --period 30d --limit 5
```

#### Sessions

```bash
# Session list with location, device, engagement data
mantecato sessions --site kerykeion.net --period 7d --limit 10

# Full event replay for a specific session
mantecato session-activity --site kerykeion.net --session-id <uuid>
```

#### Devices

```bash
# Device type breakdown (laptop, mobile, desktop, tablet)
mantecato devices --site kerykeion.net --period 30d

# Browser breakdown
mantecato devices --site kerykeion.net --dimension browser --period 30d

# OS breakdown
mantecato devices --site kerykeion.net --dimension os --period 30d

# Screen resolution breakdown
mantecato devices --site kerykeion.net --dimension screen --period 30d

# Language breakdown
mantecato devices --site kerykeion.net --dimension language --period 30d
```

#### Geographic

```bash
# Country-level breakdown
mantecato geo --site kerykeion.net --period 30d

# Region drill-down (within a country)
mantecato geo --site kerykeion.net --level region --country US --period 30d

# City drill-down
mantecato geo --site kerykeion.net --level city --country US --period 30d
```

#### Advanced Analytics

```bash
# Realtime active visitors
mantecato realtime --site kerykeion.net

# Cohort retention analysis
mantecato retention --site kerykeion.net --period 90d

# Funnel analysis (comma-separated URL steps)
mantecato funnel --site kerykeion.net --steps "/,/content/docs,/content/examples" --period 30d

# User journey paths
mantecato journeys --site kerykeion.net --period 30d --limit 10

# Revenue analytics
mantecato revenue --site kerykeion.net --period 30d

# Engagement metrics (percentiles, duration distribution)
mantecato engagement --site kerykeion.net --period 30d

# Filter value autocomplete
mantecato filter-values --site kerykeion.net --column country --period 30d
```

#### CRUD Operations

```bash
# Annotations
mantecato annotations --site kerykeion.net
mantecato annotation-create --site kerykeion.net --title "New release" --date 2026-03-21 --color green
mantecato annotation-delete --id <uuid>

# Saved Views
mantecato saved-views --site kerykeion.net
mantecato saved-view --id <uuid>
mantecato saved-view-create --site kerykeion.net --name "US Chrome users" \
  --config '{"preset":"30d","granularity":"auto","filters":["country:eq:US","browser:eq:chrome"]}'
mantecato saved-view-delete --id <uuid>

# Dashboards
mantecato dashboards
mantecato dashboard --id <uuid>
mantecato dashboard-delete --id <uuid>

# Scheduled Exports
mantecato scheduled-exports
mantecato scheduled-export --id <uuid>
mantecato scheduled-export-delete --id <uuid>
```

### Filters

Filters use the format `column:operator:value` and can be repeated:

```bash
# Single filter
mantecato stats --site kerykeion.net --filter country:eq:US

# Multiple filters (AND between different columns, OR within same column)
mantecato stats --site kerykeion.net --filter country:eq:US --filter browser:eq:chrome

# Available operators
#   eq              - equals
#   neq             - not equals
#   contains        - ILIKE %value%
#   not_contains    - NOT ILIKE %value%
#   starts_with     - ILIKE value%
#   not_starts_with - NOT ILIKE value%

# Available filter columns
#   url_path, page_title, hostname, referrer_domain,
#   utm_source, utm_medium, utm_campaign, event_name, tag,
#   browser, os, device, country, region, city, language, screen
```

### Output Formats

```bash
# Table (default) - human-readable with alignment and separators
mantecato top-pages --site kerykeion.net --format table

# JSON - for programmatic consumption
mantecato stats --site kerykeion.net --format json

# CSV - for spreadsheets and piping
mantecato pages --site kerykeion.net --format csv > pages.csv
```

---

## MCP Server

Full analytics access via the [Model Context Protocol](https://modelcontextprotocol.io/), enabling AI agents (Claude, OpenCode, etc.) to query your analytics data.

### Setup

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "mantecato": {
      "command": "npx",
      "args": ["tsx", "src/mcp/server.ts"],
      "cwd": "/path/to/mantecato",
      "env": {
        "DATABASE_URL": "postgresql://...",
        "MANTECATO_API_KEY": "mtk_..."
      }
    }
  }
}
```

Or run directly:

```bash
MANTECATO_API_KEY="mtk_..." npm run mcp
```

> Full setup guide (OpenCode, Claude Desktop, Docker): [docs/mcp-server.md](docs/mcp-server.md)

### Available Tools (41)

#### Core Analytics
| Tool | Description |
|------|-------------|
| `list_sites` | List all tracked websites |
| `get_stats` | Overview stats for a site |
| `get_timeseries` | Pageview & visitor time series |
| `get_comparison` | Compare current vs previous period |

#### Pages
| Tool | Description |
|------|-------------|
| `get_pages` | Page analytics with views, time-on-page, bounce rate |
| `get_page_detail` | Referrers, next pages, time distribution, time series for a specific page |
| `get_top_pages` | Quick top pages by visitors |

#### Sources
| Tool | Description |
|------|-------------|
| `get_sources` | Traffic sources with bounce rate and duration |
| `get_referrer_pages` | Pages a specific referrer drives traffic to |
| `get_channels` | Auto-grouped traffic channels |
| `get_utm` | UTM parameter breakdown |
| `get_click_ids` | Click ID analysis |
| `get_hostnames` | Hostname breakdown |
| `get_top_referrers` | Quick top referrers |

#### Events
| Tool | Description |
|------|-------------|
| `get_events` | Custom event metrics |
| `get_event_detail` | Time series and properties for a specific event |
| `get_top_events` | Quick top events |

#### Sessions
| Tool | Description |
|------|-------------|
| `get_sessions` | Session list with location, device, engagement data |
| `get_session_activity` | Full event replay for a session |

#### Devices & Geo
| Tool | Description |
|------|-------------|
| `get_devices` | Device/browser/OS/screen/language breakdown |
| `get_geo` | Country/region/city breakdown with drill-down |
| `get_realtime` | Real-time active visitors |

#### Advanced
| Tool | Description |
|------|-------------|
| `get_retention` | Cohort retention analysis |
| `run_funnel` | Funnel analysis with conversion rates |
| `get_journeys` | User journey paths |
| `get_revenue` | Revenue analytics |
| `get_engagement` | Engagement metrics (percentiles, distribution) |
| `get_filter_values` | Available filter values (for autocomplete) |

#### CRUD
| Tool | Description |
|------|-------------|
| `list_annotations` | List annotations for a site |
| `create_annotation` | Create annotation on timeline |
| `delete_annotation` | Delete annotation |
| `list_saved_views` | List saved views |
| `get_saved_view` | Get saved view details |
| `create_saved_view` | Create saved view (filters + date preset) |
| `delete_saved_view` | Delete saved view |
| `list_dashboards` | List custom dashboards |
| `get_dashboard` | Get dashboard details |
| `delete_dashboard` | Delete dashboard |
| `list_scheduled_exports` | List scheduled exports |
| `get_scheduled_export` | Get export details |
| `delete_scheduled_export` | Delete scheduled export |

### MCP Tool Parameters

All analytics tools accept:

| Parameter | Type | Description |
|-----------|------|-------------|
| `site` | string | Site name, domain, or UUID (required) |
| `period` | string | Date preset: `7d`, `30d`, `90d`, etc. (default: `30d`) |
| `start` | string | Custom start date (ISO 8601) |
| `end` | string | Custom end date (ISO 8601) |
| `limit` | number | Max results (default: 20) |
| `filters` | string[] | Array of `column:operator:value` strings |

Example MCP tool call:
```json
{
  "name": "get_stats",
  "arguments": {
    "site": "kerykeion.net",
    "period": "30d",
    "filters": ["country:eq:US", "browser:eq:chrome"]
  }
}
```

---

## Architecture

```
src/
  app/                    # Next.js pages and API routes
    (dashboard)/          # Authenticated dashboard pages
    api/                  # REST API endpoints (29 routes)
    login/                # Login page
    share/                # Public share pages
  cli/
    index.ts              # CLI entry point (38 commands)
    helpers.ts            # Site resolution, date/filter parsing, output formatting
  mcp/
    server.ts             # MCP server (41 tools)
  components/             # React components (layout, charts, data tables, filters)
  hooks/                  # Custom hooks (use-site-query, use-url-state, etc.)
  lib/                    # Core utilities (queries, auth, date, format, export)
  queries/                # SQL query functions (16 modules, including api-keys)
  stores/                 # Zustand stores (filters, preferences)
  types/                  # Type declarations
  generated/prisma/       # Generated Prisma client
docs/
  authentication.md       # API key system guide
  cli.md                  # Full CLI reference (38 commands)
  mcp-server.md           # MCP server setup guide (41 tools)
  docker.md               # Docker deployment guide
packages/
  tracker/                # Tracking script package (ESM + CJS + IIFE)
prisma/
  schema.prisma           # Database schema (pulled from Neon, never migrated)
```

## Important Notes

- **Read-only database**: Umami owns the schema. Only write to the `report` table (saved views, dashboards, annotations, scheduled exports). Never run Prisma migrations.
- **Port 3001**: Dev server runs on port 3001 by default.
- **`--legacy-peer-deps`**: Required for `npm install` due to react-simple-maps peer dep conflict with React 19.

## License

Private project.
