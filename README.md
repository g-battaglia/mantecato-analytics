# Mantecato

> **Pre-alpha** — APIs, CLI flags, and database assumptions may change without notice.

**AI-native analytics for Umami.** Mantecato connects to your existing Umami PostgreSQL database and makes every metric queryable by AI agents — through a 41-tool MCP server, a 38-command CLI, and a modern web dashboard. No data duplication. No new tracking script. Just plug in and analyze.

![Mantecato Dashboard](public/screenshot.png)

---

## Quick Agentic Start

Already have Node.js 22+, a Umami PostgreSQL database, and an AI coding agent? Paste this prompt into **Claude Code**, **OpenCode**, **Cursor**, or **Cline** and let it do everything:

> ```
> Clone and set up Mantecato for me. Here's what you need:
>
> 1. git clone https://github.com/g-battaglia/mantecato-analytics.git && cd mantecato-analytics
> 2. npm install --legacy-peer-deps
> 3. Copy .env.example to .env and set these values:
>    - DATABASE_URL=<my Umami PostgreSQL connection string>
>    - SESSION_SECRET=<generate a random 64-char hex string>
> 4. Run: npx prisma db pull && npx prisma generate
> 5. Start the dev server: npm run dev -- -p 3001
> 6. Open http://localhost:3001, log in with my Umami credentials,
>    go to Settings > API Keys, create a new key, and give it to me.
> 7. Add MANTECATO_API_KEY=<the key> to .env
> 8. Test the CLI works: npx tsx src/cli/index.ts sites
> 9. Once everything is running, give me a traffic report for my main site
>    using the /project:traffic-report slash command (Claude Code) or the
>    traffic-report skill (OpenCode).
> ```

Replace `<my Umami PostgreSQL connection string>` with your actual `DATABASE_URL`. The agent handles the rest — install, configure, generate the Prisma client, start the server, and run your first analysis.

---

## Your Analytics, Agent-Accessible

Mantecato ships with pre-built agent configurations for **OpenCode**, **Claude Code**, **Cline**, and **Cursor**. Point your agent at your Umami data and start asking questions:

```
You:    "Analyze traffic for the last 30 days. Which pages are losing visitors?
         Where is the best traffic coming from?"

Agent:  runs stats, compare, pages, sources, channels...
        cross-references bounce rates by source and device...

Agent:  "Traffic is up 12% (8,420 → 9,430 visitors). However, /blog/old-post
         dropped 45% and accounts for most of the bounce rate increase.
         Organic search drives 62% of quality traffic (3.2 pages/visit vs 1.4
         from social). Recommendation: redirect /blog/old-post, double down
         on SEO content."
```

No dashboard clicking. No SQL. Just ask.

---

## Two Integration Paths

| Approach | How it works | Best for |
|----------|-------------|----------|
| **MCP Server** | Agent calls 41 tools directly via [Model Context Protocol](https://modelcontextprotocol.io/) | Claude Desktop, Cursor, any MCP client |
| **CLI Agent** | Agent runs `npx tsx src/cli/index.ts <command>` in the shell | OpenCode, Claude Code, Cline, any terminal agent |

Both approaches access the same data through the same query layer. MCP is more structured (typed tool schemas, no output parsing needed). CLI is simpler to set up and works everywhere a shell is available.

---

## Agent Setup

### OpenCode

Mantecato includes a ready-to-use **site-analyst** agent and three analysis skills:

```
.opencode/
  agents/
    site-analyst.md         # CLI-based deep analytics agent
  skills/
    traffic-report/SKILL.md # Comprehensive traffic report workflow
    content-audit/SKILL.md  # Content performance audit workflow
    funnel-analysis/SKILL.md # Conversion funnel analysis workflow
```

These activate automatically when you open the project in OpenCode:

```bash
cd mantecato && opencode

# Select the site-analyst agent from the agent picker,
# or ask any question — the skills are available to all agents.
```

To also enable MCP tools, add to `~/.config/opencode/config.json`:

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

### Claude Code

Mantecato includes a comprehensive `CLAUDE.md` with full CLI instructions and three slash commands:

```bash
cd mantecato && claude

# Slash commands for common analyses:
/project:traffic-report mysite.com 30d    # Full traffic report
/project:content-audit mysite.com 30d     # Content performance audit
/project:funnel-analysis mysite.com /,/pricing,/signup  # Funnel analysis
```

Or just ask in natural language — `CLAUDE.md` teaches Claude Code the full CLI and analysis methodology.

To also enable MCP tools:

```bash
claude mcp add mantecato -- npx tsx /path/to/mantecato/src/mcp/server.ts
```

### Cline / Cursor

Both read their respective instruction files (`.clinerules`, `.cursorrules`) included in this repo. Open the project and start asking analytics questions — the agent knows all 38 CLI commands and how to chain them for deep analysis.

For MCP, add to your editor's MCP configuration:

```json
{
  "mcpServers": {
    "mantecato": {
      "command": "npx",
      "args": ["tsx", "/path/to/mantecato/src/mcp/server.ts"],
      "env": {
        "DATABASE_URL": "postgresql://...",
        "MANTECATO_API_KEY": "mtk_..."
      }
    }
  }
}
```

**Full setup guide with step-by-step instructions and examples: [docs/ai-agents.md](docs/ai-agents.md)**

---

## What's Included

```
Agent configurations          Skills / Slash commands
─────────────────────         ──────────────────────
.opencode/agents/             .opencode/skills/
  site-analyst.md               traffic-report/SKILL.md
                                content-audit/SKILL.md
CLAUDE.md                       funnel-analysis/SKILL.md
.claude/commands/
  traffic-report.md           .claude/commands/
  content-audit.md              traffic-report.md
  funnel-analysis.md            content-audit.md
                                funnel-analysis.md
.clinerules
.cursorrules
```

Every configuration is version-controlled in this repo. Fork it, customize the agents, add your own skills.

---

## CLI

Every metric from the web UI, available in your terminal.

```bash
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

38 commands covering analytics, CRUD, and data export. Full reference: **[docs/cli.md](docs/cli.md)**

---

## MCP Server

41 tools exposing the full analytics surface via Model Context Protocol. Tool reference and setup: **[docs/mcp-server.md](docs/mcp-server.md)**

---

## Web Dashboard

| Page | What it does |
|------|-------------|
| **Overview** | Pageviews, visitors, visits, bounce rate, avg duration — with time series and annotations |
| **Pages** | Per-page views, time-on-page, entries/exits, bounce rate, referrer drill-down |
| **Sources** | Referrers, UTM params, channels, click IDs, hostnames |
| **Events** | Custom event metrics with time series and property breakdown |
| **Sessions** | Session list with full event-by-event replay |
| **Devices** | Browser, OS, device type, screen size, language |
| **Geo** | Country/region/city with interactive world map |
| **Realtime** | Live active visitors and event stream |
| **Compare** | Side-by-side period comparison |
| **Retention** | Cohort retention matrix |
| **Funnels** | Multi-step conversion with drop-off rates |
| **Journeys** | Sankey diagram user path analysis |
| **Revenue** | Revenue summary, time series, breakdowns |
| **Engagement** | Session duration distribution, percentiles, bounce rates |
| **Dashboards** | Custom widget dashboards with PDF/PNG export |
| **Settings** | Site management, API key generation |

---

## Quick Start

```bash
git clone https://github.com/g-battaglia/mantecato-analytics.git
cd mantecato
npm install --legacy-peer-deps

cp .env.example .env   # edit with your Umami DB connection string

npx prisma db pull
npx prisma generate

npm run dev -- -p 3001
```

Open `http://localhost:3001` and log in with your Umami credentials.

### Container

```bash
container build -t mantecato:latest --memory 4096MB --cpus 4 .
container run -d --name mantecato -p 3000:3000 --env-file .env mantecato:latest
```

See [docs/docker.md](docs/docker.md) for Docker Compose and production deployment.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Framework | Next.js 16 (Turbopack) + React 19 |
| Database | PostgreSQL (Neon) via Prisma 7.5 |
| UI | shadcn/ui + Radix primitives |
| Charts | Recharts, react-simple-maps, d3-sankey |
| Data | TanStack Query + TanStack Table (virtualized) |
| State | Zustand |
| CLI | Commander.js v14 |
| MCP | @modelcontextprotocol/sdk v1.27 |
| Auth | JWT sessions (web), SHA-256 API keys (CLI/MCP) |

## Authentication

```bash
# Generate a key: Settings > API Keys in the web UI
export MANTECATO_API_KEY="mtk_..."
```

Keys are SHA-256 hashed before storage. Details: **[docs/authentication.md](docs/authentication.md)**

## Project Structure

```
src/
  app/            # Next.js pages + API routes (15+ pages, 29 routes)
  cli/            # CLI entry point (38 commands) + helpers
  mcp/            # MCP server (41 tools)
  components/     # React components (layout, charts, tables, filters)
  queries/        # SQL query modules (20 modules)
  lib/            # Core utilities (auth, date, format, export, queries)
  hooks/          # Custom React hooks
  stores/         # Zustand stores
docs/
  ai-agents.md    # AI agent setup guide (all platforms)
  cli.md          # Full CLI reference
  mcp-server.md   # MCP server reference
  authentication.md
  docker.md
.opencode/        # OpenCode agent + skills
.claude/          # Claude Code slash commands
```

## Requirements

- **Node.js 22+**
- **PostgreSQL** with an existing Umami database (tested with Neon)
- `npm install` requires `--legacy-peer-deps` (react-simple-maps + React 19)

## Important Notes

- **Read-only database** — Umami owns the schema. Mantecato only writes to the `report` table. Never run Prisma migrations.
- **Pre-alpha** — expect breaking changes. Functional but not battle-tested.

## License

MIT
