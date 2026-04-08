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
| **Settings** | Site management, API key generation, bot detection config |

### Bot Detection

Mantecato includes a smart bot detection system that filters out automated traffic without removing real visitors. Toggle it on from the **Bot Filter** button in the filter bar, and fine-tune it in **Settings > Bot Detection**.

The filter works at three levels:

**1. Known bots** — Sessions where the browser is identified as a bot (`searchbot`, `googlebot`, `bingbot`, crawlers, scrapers, AI bots, etc.). These are bots that don't try to hide.

**2. Empty user-agents** — Sessions with no browser and no OS recorded. These are headless HTTP clients that didn't send a User-Agent header at all.

**3. Cluster detection** — This is the core of the system. Instead of looking at individual sessions, it looks at collective patterns to catch bot farms that use real browsers (headless Chrome, Puppeteer, etc.) and are indistinguishable from real users when viewed one at a time.

How cluster detection works:

1. All sessions in the selected date range are grouped by **(country + device type)** — e.g. "HK/laptop", "US/mobile", "IT/desktop"
2. For each group, the system calculates what percentage of sessions are **single-page zero-duration bounces** (visited one page and left instantly)
3. If a group has **many sessions** (default: >100) **and** an abnormally high bounce rate (default: >90%), the group is flagged as suspicious
4. Only the bounced sessions from flagged groups are filtered — multi-page sessions from those countries are kept

This catches bot farms because they produce a statistically impossible pattern: hundreds or thousands of sessions from the same country/device combination, almost all bouncing instantly. Real traffic from any country has a mix of bounces and engaged visits.

For example, on a site receiving bot traffic from Hong Kong:

| Group | Sessions | Bounce % | Flagged? |
|-------|----------|----------|----------|
| HK/laptop | 1,513 | 96.2% | Yes — high volume + extreme bounce rate |
| SG/laptop | 1,440 | 91.5% | Yes |
| US/laptop | 2,277 | 88.1% | No — below 90% threshold, normal traffic |
| US/mobile | 1,023 | 76.3% | No |
| MX/laptop | 46 | 95.7% | No — below 100 session minimum |

Two parameters are configurable in Settings:
- **Bounce threshold** (default 90%) — the minimum bounce rate for a group to be flagged
- **Min cluster size** (default 100) — the minimum number of sessions before a group can be flagged

Additional filters available in Settings: missing screen resolution, missing language, high-velocity scraping detection (>60 pages/minute), and country exclusion lists.

The bot detection config is stored per-site in the database and shared between all users of that site. The filter bar toggle is per-user (saved in the browser).

---

## CLI

All CLI commands run from the `backend/` directory via `uv`:

```bash
cd backend

# Full analytics report — stats, sources, pages, events, channels in one shot
uv run python -m app.cli.main report --site mysite.com --period 30d

# Human-friendly report with tables and bars
uv run python -m app.cli.main report --site mysite.com --period 30d -H

# Report filtered to organic search traffic only
uv run python -m app.cli.main report --site mysite.com --period 30d --filter referrer_domain:eq:google.com

# Report as JSON for programmatic use
uv run python -m app.cli.main report --site mysite.com --period 90d --format json

# Individual queries
uv run python -m app.cli.main stats --site mysite.com --period 30d
uv run python -m app.cli.main pages --site mysite.com --limit 10 --format json
uv run python -m app.cli.main funnel --site mysite.com --steps "/,/pricing,/signup"
uv run python -m app.cli.main devices --site mysite.com --dimension browser --filter country:eq:US
```

45 commands covering analytics queries, CRUD operations, and data export. Full reference: **[docs/cli.md](docs/cli.md)**

---

## AI Agent Integrations

Works with **Claude Code**, **OpenCode**, **OpenClaw**, **Cline**, **Cursor**, and any MCP-compatible client.

### CLI mode (any agent with shell access)

From the `backend/` directory, the agent runs `uv run python -m app.cli.main <command>` to query your data. Works with Claude Code, OpenCode, Cline, Cursor — anything that can execute shell commands.

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

Mantecato runs as two containers (frontend + backend) connecting to your existing Umami PostgreSQL database.

### 1. Configure

```bash
cp .env.example .env
```

Edit `.env` with your database connection:

```env
DATABASE_URL="postgresql://user:password@host:5432/umami"
SESSION_SECRET="any-random-string-here"
```

### 2. Start

```bash
# Build and run (Docker or Apple Containers)
docker compose up -d --build
```

The dashboard is at **http://localhost:4180**. Log in with your Umami credentials.

### 3. CLI and MCP (optional)

```bash
# Run CLI commands via Docker
docker compose --profile cli run --rm cli report --site mysite.com --period 30d

# Start MCP server for AI agents
docker compose --profile mcp run --rm mcp
```

### Compatibility

The `docker-compose.yaml` uses standard OCI images and works with:
- **Docker Desktop** (macOS, Windows, Linux)
- **Apple Containers** (`container compose up -d --build`)
- **Podman** (`podman compose up -d --build`)
- Any OCI-compliant runtime

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

Copyright (c) 2025 Giacomo Battaglia

This project is licensed under the **GNU Affero General Public License v3.0** (AGPLv3). See [LICENSE](LICENSE) for the full text.

### What this means

- You can **freely install, use, and modify** Mantecato for any purpose
- If you modify and deploy it as a network service, you must **share your changes** under AGPLv3
- You **cannot** incorporate it into proprietary software without a commercial license

### Commercial / Dual Licensing

A **commercial license** is available for organizations that need to:
- Embed Mantecato in proprietary products
- Deploy modified versions without source disclosure
- Get custom installations, support, or SLA guarantees

Contact **giacomo@mantecato.com** for licensing and custom deployment options.
