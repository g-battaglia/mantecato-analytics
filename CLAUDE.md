# Mantecato — Claude Code Instructions

Mantecato is a standalone analytics dashboard that reads an existing Umami PostgreSQL database. It provides a web UI, a 45-command CLI, a 41-tool MCP server, and a JS tracker.

**Detailed docs:** see `.claude/wiki/` — architecture, deployment, all commands, MCP tools, frontend stack.

## Architecture

```
core/       mantecato-core     Shared query engine, DB, filters (asyncpg only)
backend/    mantecato-backend  FastAPI REST API
cli/        mantecato-cli      45-command CLI (typer, rich, textual)
mcp/        mantecato-mcp      41-tool MCP server (stdio + HTTP)
frontend/                      Vite 6 + React 19 SPA
packages/tracker/              @mantecato/tracker JS tracking script
```

All queries live in `core/mantecato_core/queries/` — shared by backend, CLI, and MCP. No ORM — raw SQL with `{{param::type}}` substitution.

Do not add or rely on `next/*` APIs.

## Running

```bash
cd cli && uv run mantecato <command> -s <site> -p 30d       # CLI
cd backend && uv run uvicorn app.main:app --port 8100       # API
cd frontend && npm run dev                                   # Frontend
cd mcp && PYTHONPATH=../core uv run mantecato-mcp           # MCP (stdio)
```

`DATABASE_URL` and `MANTECATO_API_KEY` are already configured in `.env`.

## CLI Quick Reference

**Global options:** `-s <site>`, `-p <period>`, `--filter <col:op:val>`, `-f json|table|csv`, `-l <limit>`

**Key commands:** `report`, `stats`, `compare`, `pages`, `sources`, `events`, `devices`, `geo`, `sessions`, `realtime`, `retention`, `funnel`, `journeys`, `engagement`

**Filter syntax:** `column:operator:value` (e.g. `device:eq:mobile`, `referrer_domain:contains:google`)

Full command list and details: `.claude/wiki/cli.md`

## Analysis Methodology

1. **Start with context** — `report` for full picture, or `stats` + `compare`
2. **Go wide, then deep** — high-level breakdowns first, drill into anomalies
3. **Use JSON for computation** — `--format json` for analysis, `--format table` for presentation
4. **Cross-reference** — combine filters for insights (mobile + organic, country + bounce rate)
5. **Always compare periods** — contextualize with deltas
6. **Run independent commands in parallel**

## Output Format

1. **Executive Summary** — 2-3 sentences, lead with key takeaway
2. **Key Metrics** — numbers with period-over-period deltas
3. **Findings** — organized by theme
4. **Recommendations** — specific, actionable next steps

Always include actual numbers: "traffic increased 23% (1,240 → 1,525 visitors)".

## Rules

- **Never guess data** — always run the CLI command
- **Read-only database** — never run migrations or write to Umami tables
- **Present insights, not data dumps**
