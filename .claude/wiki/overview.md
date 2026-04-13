# Overview

Mantecato is a standalone analytics dashboard that reads an existing Umami PostgreSQL database. It provides a web UI, a 45-command CLI, a 41-tool MCP server, and a JavaScript tracker.

## Package Structure

```
core/       mantecato-core     Shared query engine, DB, filters (no framework deps)
backend/    mantecato-backend  FastAPI REST API (depends on core)
cli/        mantecato-cli      Terminal CLI (depends on core, typer, rich, textual)
mcp/        mantecato-mcp      MCP server (depends on core, mcp, uvicorn, starlette)
frontend/                      Vite + React 19 SPA
packages/
  tracker/  @mantecato/tracker JS tracking script (Umami wire-compatible)
```

## Dependency Graph

```
core (asyncpg only)
 ├── backend (+ fastapi, python-jose, bcrypt, pydantic-settings)
 ├── cli     (+ typer, rich, textual)
 └── mcp     (+ mcp, httpx, uvicorn, starlette)

frontend (standalone, talks to backend via REST)
tracker  (standalone JS, sends to /api/send)
```

## Key Architectural Patterns

1. **Shared query modules** — All SQL lives in `core/mantecato_core/queries/` (23 modules). Backend routes, CLI commands, and MCP tools all import from the same place. Zero duplication.

2. **Raw SQL with parameter substitution** — No ORM. Custom `{{param::type}}` placeholder syntax compiled to positional `$1, $2` args for asyncpg.

3. **Composable filter system** — User-friendly `column:operator:value` strings → parameterized WHERE clauses. 16 columns, 6 operators.

4. **Read-only Umami DB** — Never writes to Umami schema tables. Internal tables (reports, API keys, annotations) use separate rows.

5. **Three-tier bot detection** — Known UA patterns + empty UA + statistical cluster detection. Configurable per-site.

6. **No Next.js** — Migrated to pure Vite + React. Do not introduce next/* APIs.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string (Umami DB) |
| `SESSION_SECRET` | JWT signing key |
| `MANTECATO_API_KEY` | API key for CLI/MCP auth |
| `CRON_SECRET` | Optional cron endpoint token |
| `CORS_ORIGINS` | Comma-separated allowed origins |
| `ENVIRONMENT` | `development` or `production` |
