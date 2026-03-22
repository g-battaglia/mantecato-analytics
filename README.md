# Mantecato

> **Pre-alpha** — This project is under active development. APIs, CLI flags, and database assumptions may change without notice. Use at your own risk.

**Deep analytics for Umami users who need more.** Mantecato is a standalone analytics dashboard that connects to your existing Umami PostgreSQL database and unlocks advanced analysis — funnels, retention cohorts, journey mapping, revenue tracking, session replay, and more — through a modern web UI, a 38-command CLI, and a 41-tool MCP server for AI agents.

No data duplication. No new tracking script required. Just point it at your Umami database and go.

---

## Why Mantecato

Umami is great at collecting data. Mantecato is built to **analyze** it.

- **15+ analytics pages** — from basic pageviews to cohort retention, funnel conversion, and Sankey journey diagrams
- **38 CLI commands** — every metric available in the web UI, queryable from the terminal with JSON, table, or CSV output
- **41 MCP tools** — let Claude, OpenCode, or any MCP-compatible agent query your analytics programmatically
- **Advanced filters** — combine any dimension (country, browser, UTM, page, event) with AND/OR logic
- **Realtime** — live active visitors and event stream
- **Custom dashboards** — drag-and-drop widget builder with PDF/PNG export
- **Read-only by design** — Mantecato never touches your Umami schema; it only writes to a single `report` table for its own features (saved views, annotations, dashboards, API keys)

## Stack

| Layer | Technology |
|-------|-----------|
| Framework | Next.js 16 (Turbopack) + React 19 |
| Database | PostgreSQL (Neon) via Prisma 7.5 client engine |
| UI | shadcn/ui + Radix primitives |
| Charts | Recharts, react-simple-maps (world choropleth), d3-sankey |
| Data | TanStack Query + TanStack Table (virtualized) |
| State | Zustand |
| CLI | Commander.js v14 |
| MCP | @modelcontextprotocol/sdk v1.27 |
| Auth | JWT sessions (web), SHA-256 hashed API keys (CLI/MCP) |

---

## Quick Start

```bash
git clone https://github.com/g-battaglia/mantecato-analytics.git
cd mantecato
npm install --legacy-peer-deps

# Configure
cp .env.example .env   # then edit with your Umami DB connection string

# Generate Prisma client (read-only, never migrate)
npx prisma db pull
npx prisma generate

# Start
npm run dev -- -p 3001
```

Open `http://localhost:3001` and log in with your Umami credentials.

### Container (Apple Containers / Docker)

```bash
container build -t mantecato:latest --memory 4096MB --cpus 4 .
container run -d --name mantecato -p 3000:3000 --env-file .env mantecato:latest
```

See [docs/docker.md](docs/docker.md) for Docker Compose, CLI/MCP via container, and production tips.

---

## Web Dashboard

| Page | What it does |
|------|-------------|
| **Overview** | Pageviews, visitors, visits, bounce rate, avg duration, pages/visit — with time series and annotations |
| **Pages** | Per-page views, time-on-page, entries/exits, bounce rate, plus drill-down to referrers and next-page flow |
| **Sources** | Referrers, UTM params, channels, click IDs, hostnames, and referrer-to-page drill-down |
| **Events** | Custom event metrics with time series and property breakdown |
| **Sessions** | Session list with full event-by-event replay timeline |
| **Devices** | Browser, OS, device type, screen size, language — with donut charts |
| **Geo** | Country/region/city breakdown with interactive world map choropleth |
| **Realtime** | Live active visitors and recent event stream |
| **Compare** | Side-by-side current vs previous period comparison |
| **Retention** | Cohort retention matrix |
| **Funnels** | Multi-step conversion funnels with drop-off rates |
| **Journeys** | User path analysis with Sankey diagram |
| **Revenue** | Revenue summary, time series, breakdown by event and country |
| **Engagement** | Session duration distribution, percentiles, bounce rate by page/source |
| **Dashboards** | Drag-and-drop custom widget dashboards with PDF/PNG export |
| **Settings** | Site management, API key generation |

Additional capabilities: saved views, timeline annotations, scheduled exports, public share links, table virtualization for large datasets.

---

## CLI

Every metric from the web UI, available in your terminal.

```bash
# Set your API key (required for write operations)
export MANTECATO_API_KEY="mtk_..."

# Overview stats
npm run cli -- stats --site mysite.com --period 30d

# Top pages as JSON
npm run cli -- pages --site mysite.com --limit 10 --format json

# Funnel analysis
npm run cli -- funnel --site mysite.com --steps "/,/pricing,/signup"

# Filtered by country and browser
npm run cli -- devices --site mysite.com --dimension browser --filter country:eq:US
```

38 commands covering all analytics, CRUD operations, and data export. Full reference: **[docs/cli.md](docs/cli.md)**

---

## MCP Server

Connect your AI agent to your analytics data via the [Model Context Protocol](https://modelcontextprotocol.io/).

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

41 tools covering the full analytics surface. Setup guides for OpenCode, Claude Desktop, and Docker: **[docs/mcp-server.md](docs/mcp-server.md)**

---

## Authentication

The web dashboard uses session-based JWT auth. The CLI and MCP server use **API keys**.

```bash
# Generate: Settings > API Keys > New Key (in the web UI)
export MANTECATO_API_KEY="mtk_..."
```

Keys are SHA-256 hashed before storage. The raw key is shown once at creation. Full details: **[docs/authentication.md](docs/authentication.md)**

---

## Project Structure

```
src/
  app/                    # Next.js pages and API routes
    (dashboard)/          # Authenticated dashboard pages (15+)
    api/                  # REST API endpoints (29 routes)
  cli/                    # CLI entry point (38 commands) + helpers
  mcp/                    # MCP server (41 tools)
  components/             # React components (layout, charts, tables, filters)
  queries/                # SQL query modules (16 modules)
  lib/                    # Core utilities (auth, date, format, export, queries)
  hooks/                  # Custom React hooks
  stores/                 # Zustand stores
docs/
  authentication.md       # API key system
  cli.md                  # Full CLI reference
  mcp-server.md           # MCP server setup
  docker.md               # Container deployment
packages/
  tracker/                # Optional tracking script (ESM + CJS + IIFE)
```

## Requirements

- **Node.js 22+**
- **PostgreSQL** with an existing Umami database (tested with Neon)
- `npm install` requires `--legacy-peer-deps` (react-simple-maps + React 19)

## Important Notes

- **Read-only database** — Umami owns the schema. Mantecato only writes to the `report` table. Never run Prisma migrations.
- **Pre-alpha** — expect breaking changes. The project is functional but not yet battle-tested in production.
- **Port 3001** — dev server defaults to 3001 to avoid conflicts.

## License

MIT
