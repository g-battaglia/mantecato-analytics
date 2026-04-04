# Mantecato

Analytics platform that connects directly to your [Umami](https://umami.is) PostgreSQL database. Provides a **Vite + React dashboard**, a **FastAPI backend**, a **45-command Python CLI**, and a **41-tool MCP server** — so you can explore your data from the browser, the terminal, or your AI coding agent.

![Mantecato Dashboard](public/screenshot.png)

## Quick Start

```bash
git clone https://github.com/g-battaglia/mantecato-analytics.git
cd mantecato-analytics

# Install dependencies
npm --prefix frontend install
uv sync --project backend

# Configure
cp .env.example .env
# Edit .env — add DATABASE_URL (your Umami DB) and SESSION_SECRET

# Start both servers
./dev.sh start
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
frontend/          Vite + React 19 SPA (port 4180)
backend/
  app/
    routers/       FastAPI route handlers
    queries/       Shared SQL query modules (used by API, CLI, and MCP)
    cli/           Python CLI — 45 commands (Typer + Rich)
    mcp/           Python MCP server — 41 tools
    filters.py     Filter parsing and SQL building
    database.py    asyncpg connection pool
    date_utils.py  Date range resolution
packages/tracker/  Lightweight tracking script
```

The entire backend stack is Python. The CLI and MCP server share the same query modules as the API — no code duplication.

Mantecato is **read-only** against your Umami database. The only writes go to internal tables (API keys, saved views, dashboards).

---

## Web Dashboard

15 analytics pages plus a custom dashboard builder:

| Page | Description |
|------|-------------|
| **Overview** | Pageviews, visitors, bounce rate, time series, top sections, channels, events with inline property breakdown |
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
| **Dashboards** | Custom drag-and-drop widget dashboards with PDF/PNG export |
| **Settings** | Site management, API key generation |

---

## CLI

All CLI commands run via `uv`:

```bash
# Full analytics report — stats, sources, pages, events, channels in one shot
uv run --project backend python -m app.cli.main report --site mysite.com --period 30d

# Human-friendly report with tables and bars
uv run --project backend python -m app.cli.main report --site mysite.com --period 30d -H

# Report filtered to organic search traffic only
uv run --project backend python -m app.cli.main report --site mysite.com --period 30d --filter referrer_domain:eq:google.com

# Report as JSON for programmatic use
uv run --project backend python -m app.cli.main report --site mysite.com --period 90d --format json

# Individual queries
uv run --project backend python -m app.cli.main stats --site mysite.com --period 30d
uv run --project backend python -m app.cli.main pages --site mysite.com --limit 10 --format json
uv run --project backend python -m app.cli.main funnel --site mysite.com --steps "/,/pricing,/signup"
uv run --project backend python -m app.cli.main devices --site mysite.com --dimension browser --filter country:eq:US
```

45 commands covering analytics queries, CRUD operations, and data export. Full reference: **[docs/cli.md](docs/cli.md)**

---

## AI Agent Integrations

Works with **Claude Code**, **OpenCode**, **OpenClaw**, **Cline**, **Cursor**, and any MCP-compatible client.

### CLI mode (any agent with shell access)

The agent runs `uv run --project backend python -m app.cli.main <command>` to query your data. Works with Claude Code, OpenCode, Cline, Cursor — anything that can execute shell commands.

### MCP mode (structured tool calls)

Add to your editor's MCP configuration:

```json
{
  "mcpServers": {
    "mantecato": {
      "command": "uv",
      "args": ["run", "--project", "backend", "python", "-m", "app.mcp.server"],
      "cwd": "/path/to/mantecato-analytics",
      "env": {
        "DATABASE_URL": "postgresql://...",
        "MANTECATO_API_KEY": "mtk_..."
      }
    }
  }
}
```

### Ready-to-use configs

| Tool | What's included |
|------|----------------|
| **OpenCode** | `site-analyst` agent + 3 analysis skills |
| **Claude Code** | `CLAUDE.md` + 3 slash commands |
| **OpenClaw** | 3 analysis skills in `.openclaw/` |
| **Cline** | `.clinerules` with full CLI reference |
| **Cursor** | `.cursorrules` with full CLI reference |

See **[docs/ai-agents.md](docs/ai-agents.md)** for platform-specific setup instructions.

---

## Docker

```bash
# Full stack
docker compose up -d --build

# CLI only (optional profile)
docker compose --profile cli run --rm cli report --site mysite.com

# MCP server (optional profile)
docker compose --profile mcp run --rm mcp
```

Production guide: **[docs/docker.md](docs/docker.md)**

---

## Documentation

| Doc | Content |
|-----|---------|
| **[AI Agent Setup](docs/ai-agents.md)** | Step-by-step for each platform |
| **[CLI Reference](docs/cli.md)** | All 45 commands, options, filters, examples |
| **[MCP Server](docs/mcp-server.md)** | All 41 tools, parameters, examples |
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
| CLI | Typer + Rich |
| MCP | mcp Python SDK |
| Database | PostgreSQL (direct asyncpg) |
| Auth | JWT sessions (web), SHA-256 API keys (CLI/MCP) |

## License

MIT
