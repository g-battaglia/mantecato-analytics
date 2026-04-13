# Mantecato

Analytics platform that connects directly to your [Umami](https://umami.is) PostgreSQL database. Provides a **Vite + React dashboard**, a **FastAPI backend**, a **45-command Python CLI**, a **41-tool MCP server**, and a **JavaScript tracker** — so you can explore your data from the browser, the terminal, or your AI agent.

![Mantecato Dashboard](public/screenshot.png)

## Quick Start

```bash
git clone https://github.com/g-battaglia/mantecato-analytics.git
cd mantecato-analytics

# Configure
cp .env.example .env
# Edit .env — add DATABASE_URL (your Umami DB) and SESSION_SECRET

# Frontend
cd frontend && npm install && npm run dev

# Backend
cd backend && uv run uvicorn app.main:app --port 8100 --reload
```

The dashboard opens at **http://localhost:4180** (log in with your Umami credentials).
The API runs on **http://localhost:8100**.

### API Key

Required for the CLI, MCP server, and AI agent integrations:

1. Open the dashboard → **Settings → API Keys**
2. Click **New Key** and copy the key (`mtk_...`)
3. Add it to `.env`: `MANTECATO_API_KEY=mtk_...`

---

## Architecture

```
core/                  mantecato-core — shared query engine, DB, filters (no framework deps)
backend/               mantecato-backend — FastAPI REST API
cli/                   mantecato-cli — 45-command terminal interface
mcp/                   mantecato-mcp — 41-tool MCP server (stdio + HTTP)
frontend/              Vite 6 + React 19 SPA
packages/tracker/      @mantecato/tracker — JS tracking script (Umami-compatible)
```

All queries live in `core/mantecato_core/queries/` — shared by the API, CLI, and MCP server. No ORM — raw SQL with asyncpg.

Mantecato is **read-only** against your Umami database. The only writes go to internal tables (API keys, saved views, dashboards, annotations).

---

## Web Dashboard

15 analytics pages plus a custom dashboard builder:

| Page | Description |
|------|-------------|
| **Overview** | Pageviews, visitors, bounce rate, time series, top sections, channels, events |
| **Pages** | Per-page views, time-on-page, entries/exits, bounce rate |
| **Sources** | Referrers, UTM parameters, channels, click IDs |
| **Events** | Custom event metrics with property breakdown |
| **Sessions** | Session list with full event-by-event replay |
| **Devices** | Browser, OS, device type, screen size, language |
| **Geo** | Country/region/city with interactive world map |
| **Realtime** | Live active visitors and event stream |
| **Compare** | Side-by-side period comparison |
| **Retention** | Cohort retention matrix |
| **Funnels** | Multi-step conversion with drop-off rates |
| **Journeys** | Sankey diagram of user paths |
| **Revenue** | Revenue summary, time series, breakdowns |
| **Engagement** | Session duration distribution and percentiles |
| **Dashboards** | Custom widget dashboards with PDF/PNG export |

### Bot Detection

Smart three-tier bot detection: known UA patterns, empty user-agents, and statistical cluster detection (groups sessions by country+device, flags high-volume groups with >90% bounce rate). Configurable per-site in Settings.

---

## CLI

```bash
cd cli

# Full analytics report
uv run mantecato report --site mysite.com --period 30d

# Filtered to mobile traffic
uv run mantecato report --site mysite.com -p 30d --filter device:eq:mobile

# JSON output for programmatic use
uv run mantecato stats --site mysite.com -p 90d -f json

# Conversion funnel
uv run mantecato funnel --site mysite.com --steps "/,/pricing,/signup"

# Individual queries with filters
uv run mantecato pages --site mysite.com --filter referrer_domain:contains:google
uv run mantecato devices --site mysite.com --dimension browser --filter country:eq:US
```

**Global options:** `-s <site>`, `-p <period>`, `--filter <col:op:val>`, `-f json|table|csv`, `-l <limit>`, `-g <granularity>`

**Filter syntax:** `column:operator:value` — 16 columns × 6 operators. Repeatable.

45 commands covering analytics queries, CRUD operations, config management, and a terminal UI. Full reference: **[docs/cli.md](docs/cli.md)**

---

## MCP Server

41 tools for AI agent integration. Supports **stdio** (local) and **HTTP** (remote) transports.

### Local (stdio) — Claude Desktop, Claude Code, Cursor, etc.

```json
{
  "mcpServers": {
    "mantecato": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mantecato/mcp", "mantecato-mcp"],
      "env": {
        "DATABASE_URL": "postgresql://...",
        "MANTECATO_API_KEY": "mtk_...",
        "PYTHONPATH": "/path/to/mantecato/core"
      }
    }
  }
}
```

### Remote (HTTP) — Claude.ai, remote agents

The MCP server can be deployed as an HTTP service with OAuth 2.0 authentication:

```bash
# Start HTTP server
cd mcp && PYTHONPATH=../core DATABASE_URL=... MCP_API_KEY=... \
  uv run mantecato-mcp --transport http --port 8200
```

Connect from any MCP client:

```json
{
  "mcpServers": {
    "mantecato": {
      "url": "https://your-deployment.example.com/mcp",
      "headers": { "Authorization": "Bearer <MCP_API_KEY>" }
    }
  }
}
```

For Claude.ai, add via **Settings → Integrations → Add custom connector** with OAuth Client ID and Client Secret.

Full tool reference: **[docs/mcp-server.md](docs/mcp-server.md)**

---

## Tracker

`@mantecato/tracker` — lightweight JavaScript tracking script, wire-compatible with Umami's `/api/send` endpoint.

```html
<script defer src="https://your-instance.com/api/script"
        data-website-id="your-site-uuid"></script>
```

Or use programmatically:

```typescript
import { createTracker } from '@mantecato/tracker';

const tracker = createTracker({
  websiteId: 'your-site-uuid',
  baseUrl: 'https://your-instance.com',
});

tracker.pageview();
tracker.event('button_click', { variant: 'cta' });
tracker.revenue(29.99, 'USD');
```

---

## Docker

```bash
cp .env.example .env
# Edit .env with DATABASE_URL and SESSION_SECRET

docker compose up -d --build
```

Dashboard at **http://localhost:4180**, API at **http://localhost:8100**.

```bash
# CLI via Docker
docker compose --profile cli run --rm cli report --site mysite.com -p 30d

# MCP server via Docker
docker compose --profile mcp run --rm mcp
```

Works with Docker Desktop, Apple Containers, Podman, or any OCI-compliant runtime.

Production guide: **[docs/docker.md](docs/docker.md)**

---

## AI Agent Setup

Works with **Claude Code**, **Claude.ai**, **Claude Desktop**, **OpenCode**, **Cline**, **Cursor**, and any MCP-compatible client.

| Mode | Best for |
|------|----------|
| **CLI** | Any agent with shell access — run `cd cli && uv run mantecato <command>` |
| **MCP (stdio)** | Local agents — structured tool calls via stdin/stdout |
| **MCP (HTTP)** | Remote agents — deployed as HTTP service with Bearer auth |

Claude Code includes 4 slash commands: `/analytics`, `/traffic-report`, `/content-audit`, `/funnel-analysis`.

See **[docs/ai-agents.md](docs/ai-agents.md)** for platform-specific setup.

---

## Documentation

| Doc | Content |
|-----|---------|
| **[AI Agent Setup](docs/ai-agents.md)** | Step-by-step for each platform |
| **[CLI Reference](docs/cli.md)** | All 45 commands, options, filters, examples |
| **[MCP Server](docs/mcp-server.md)** | All 41 tools, parameters, transport modes |
| **[Authentication](docs/authentication.md)** | API key generation and security |
| **[Docker](docs/docker.md)** | Container deployment and production tips |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Vite 6 + React 19 + React Router 7 |
| Styling | Tailwind CSS 4 + shadcn/ui + Radix |
| Charts | Recharts, react-simple-maps, d3-sankey |
| Data | TanStack Query + TanStack Table (virtualized) |
| State | Zustand |
| Backend | FastAPI + Uvicorn + asyncpg |
| CLI | Typer + Rich + Textual |
| MCP | mcp Python SDK (stdio + StreamableHTTP) |
| Tracker | TypeScript, ESM + CJS + UMD |
| Database | PostgreSQL (direct asyncpg, no ORM) |
| Auth | JWT sessions (web), SHA-256 API keys (CLI/MCP), OAuth 2.0 (remote MCP) |

## License

Copyright (c) 2025 Giacomo Battaglia

This project is licensed under the **GNU Affero General Public License v3.0** (AGPLv3). See [LICENSE](LICENSE) for the full text.

### What this means

- You can **freely install, use, and modify** Mantecato for any purpose
- If you modify and deploy it as a network service, you must **share your changes** under AGPLv3
- You **cannot** incorporate it into proprietary software without a commercial license

### Commercial / Dual Licensing

A **commercial license** is available for organizations that need to embed Mantecato in proprietary products, deploy modified versions without source disclosure, or get custom installations and support.

Contact **giacomo@mantecato.com** for licensing and custom deployment options.
