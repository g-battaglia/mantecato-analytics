# CLI & MCP Migration Plan: TypeScript → Python

## Goal

Migrate the CLI (45 commands, 1,134 lines) and MCP server (41 tools, 1,075 lines) from TypeScript to Python, eliminating the `src/` directory entirely. After migration, the entire codebase is Python (backend) + React (frontend) — no more Node.js runtime required for server-side operations.

## Current State

```
src/
  cli/
    index.ts          1,134 lines — 45 commands (Commander.js)
    helpers.ts          234 lines — shared utilities
  mcp/
    server.ts         1,075 lines — 41 tools (@modelcontextprotocol/sdk)
  queries/              20 modules — raw SQL queries via Prisma
  lib/
    queries.ts        — rawQuery() via Prisma $queryRawUnsafe
    date.ts           — date range resolution
    format.ts         — formatDuration, formatPercent
    constants.ts      — presets, granularities
    prisma.ts         — Prisma client singleton
    filters.ts        — Filter type + SQL builder
```

**Key fact**: `backend/app/queries/` already has Python equivalents for all 20 TS query modules. The SQL is identical — both use the same `{{param::type}}` placeholder syntax. The Python versions use `asyncpg` directly instead of Prisma.

## Target State

```
backend/
  app/
    cli/
      __init__.py
      main.py            — Click/Typer entrypoint, all 45 commands
      helpers.py          — output formatting, table rendering, bars
      report.py           — report command (complex, keep separate)
    mcp/
      server.py           — 41 tools via mcp Python SDK
    queries/              — unchanged (already Python)
    routers/              — unchanged
    ...
```

Entry points:
- CLI: `python -m backend.app.cli.main` or a `pyproject.toml` script entry
- MCP: `python -m backend.app.mcp.server` (stdio transport)

---

## Phase 1: CLI Migration

### 1.1 Choose CLI framework

Use **Typer** (built on Click). Reasons:
- Type hints → automatic argument parsing (like Commander.js)
- Built-in `--help` generation
- `typer.Option()` for flags like `-s`, `-p`, `-f`, `-H`
- Async support via `asyncio.run()`

Add to `backend/pyproject.toml`:
```toml
dependencies = [
    ...
    "typer[all]>=0.15",
    "rich>=13.0",      # for table formatting in -H mode
]
```

### 1.2 Create `backend/app/cli/helpers.py`

Port these from `src/cli/helpers.ts`:

| TS function | Python equivalent | Notes |
|---|---|---|
| `listSites()` | Reuse `backend/app/queries/stats.py` or write standalone query | Direct `asyncpg` query |
| `resolveSiteId(name)` | Same logic — fuzzy match on name/domain/uuid | |
| `parseDateArgs(period, start, end)` | Reuse `backend/app/date_utils.py` — already has `resolve_date_range()` | Direct reuse |
| `resolveGranularityArg()` | Already in `backend/app/date_utils.py` as `resolve_granularity()` | Direct reuse |
| `parseFilterArgs(strings)` | Already in `backend/app/filters.py` as `parse_filters_from_params()` | Direct reuse |
| `formatOutput(data, format)` | Rewrite using `rich.table.Table` for table, `json.dumps` for json, `csv.writer` for csv | |
| `computeDerivedStats(raw)` | Port — simple math (bounce rate, avg duration, pages/visit) | |
| `num(n)` | `f"{n:,}"` | |
| `pctChange(cur, prev)` | Port — 5 lines | |

**Key insight**: Most helper logic already exists in `backend/app/`. The CLI helpers are thin wrappers.

### 1.3 Create `backend/app/cli/main.py`

Structure:
```python
import asyncio
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="mantecato", help="Mantecato Analytics CLI")
console = Console()

# Common options as a callback
@app.callback()
def main(): pass

@app.command()
def stats(
    site: str = typer.Option(..., "-s", "--site"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None),
    end: str = typer.Option(None),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
    limit: int = typer.Option(20, "-l", "--limit"),
    granularity: str = typer.Option("auto", "-g", "--granularity"),
):
    asyncio.run(_stats(site, period, start, end, format, filter, limit, granularity))

async def _stats(site, period, start, end, fmt, filters, limit, granularity):
    from ..queries import stats as q
    from ..database import get_pool, close_pool
    # ... resolve site, dates, run query, format output
```

### 1.4 Command-by-command mapping

Every CLI command maps to an existing Python query module. Here is the complete mapping:

| CLI Command | Python query module | Function to call |
|---|---|---|
| `sites` | Direct SQL | `SELECT website_id, name, domain FROM website` |
| `stats` | `queries/stats.py` | `get_website_stats()` |
| `timeseries` | `queries/stats.py` | `get_pageview_time_series()` |
| `compare` | `queries/compare.py` | `get_comparison()` |
| `report` | Multiple (see 1.5) | Custom composition |
| `pages` | `queries/pageviews.py` | `get_page_metrics()` |
| `page-detail` | `queries/pageviews.py` | `get_page_detail()` |
| `top-pages` | `queries/stats.py` | `get_top_pages()` |
| `sources` | `queries/sources.py` | `get_referrer_metrics()` |
| `referrer-pages` | `queries/sources.py` | `get_referrer_page_metrics()` |
| `channels` | `queries/sources.py` | `get_channel_metrics()` |
| `utm` | `queries/sources.py` | `get_utm_metrics()` |
| `clickids` | `queries/sources.py` | `get_click_id_metrics()` |
| `hostnames` | `queries/sources.py` | `get_hostname_metrics()` |
| `top-referrers` | `queries/stats.py` | `get_top_referrers()` |
| `events` | `queries/events.py` | `get_event_metrics()` |
| `event-detail` | `queries/events.py` | `get_event_time_series()` + `get_event_properties()` |
| `top-events` | `queries/stats.py` | `get_top_events()` |
| `sessions` | `queries/sessions.py` | `get_sessions()` |
| `session-activity` | `queries/sessions.py` | `get_session_activity()` |
| `devices` | `queries/devices.py` | `get_device_breakdown()` |
| `geo` | `queries/geo.py` | `get_geo_breakdown()` |
| `realtime` | `queries/realtime.py` | `get_realtime()` |
| `retention` | `queries/retention.py` | `get_retention()` |
| `funnel` | `queries/funnels.py` | `get_funnel()` |
| `journeys` | `queries/journeys.py` | `get_journeys()` |
| `revenue` | `queries/revenue.py` | `get_revenue_summary()` etc. |
| `engagement` | `queries/engagement.py` | `get_engagement()` |
| `filter-values` | `queries/filter_values.py` | `get_filter_values()` |
| `annotations` | `queries/annotations.py` | `list_annotations()` |
| `annotation-create` | `queries/annotations.py` | `create_annotation()` |
| `annotation-delete` | `queries/annotations.py` | `delete_annotation()` |
| `saved-views` | `queries/saved_views.py` | `list_saved_views()` |
| `saved-view` | `queries/saved_views.py` | `get_saved_view()` |
| `saved-view-create` | `queries/saved_views.py` | `create_saved_view()` |
| `saved-view-delete` | `queries/saved_views.py` | `delete_saved_view()` |
| `dashboards` | `queries/dashboards.py` | `list_dashboards()` |
| `dashboard` | `queries/dashboards.py` | `get_dashboard()` |
| `dashboard-delete` | `queries/dashboards.py` | `delete_dashboard()` |
| `scheduled-exports` | `queries/scheduled_exports.py` | `list_scheduled_exports()` |
| `scheduled-export` | `queries/scheduled_exports.py` | `get_scheduled_export()` |
| `scheduled-export-delete` | `queries/scheduled_exports.py` | `delete_scheduled_export()` |

### 1.5 Report command (`backend/app/cli/report.py`)

The `report` command is the most complex. It:
1. Runs 6 queries in parallel via `asyncio.gather()`
2. Fetches event properties for each top event (second pass)
3. Has 3 output modes: default compact, `-H` human-friendly with `rich` tables and bars, `-f json`

Port the entire logic from `src/cli/index.ts` lines 800-978. Use `rich.table.Table` for the `-H` mode instead of manual box-drawing characters. This will be cleaner and handle terminal width automatically.

### 1.6 Output formatting with Rich

Replace the manual table rendering with `rich`:

```python
from rich.table import Table
from rich.console import Console
from rich.bar import Bar

console = Console()

# Example: Top Pages table
table = Table(title="Top Pages", show_header=True)
table.add_column("Page", style="cyan", max_width=40)
table.add_column("Visitors", justify="right")
table.add_column("Views", justify="right")
table.add_column("", width=20)  # bar column

for p in pages:
    bar_width = int((p["visitors"] / max_visitors) * 20)
    bar = "█" * bar_width + "░" * (20 - bar_width)
    table.add_row(p["url_path"], f'{p["visitors"]:,}', f'{p["views"]:,}', bar)

console.print(table)
```

### 1.7 Entry point

In `backend/pyproject.toml`:
```toml
[project.scripts]
mantecato = "backend.app.cli.main:app"
```

Or simpler, in the repo root `package.json` replace:
```json
"cli": "npx tsx src/cli/index.ts"
```
with:
```json
"cli": "python -m backend.app.cli.main"
```

### 1.8 Database connection lifecycle

The TS CLI uses Prisma (auto-connects, auto-disconnects). The Python CLI needs explicit pool management:

```python
async def run_with_db(coro):
    """Initialize connection pool, run coroutine, close pool."""
    from ..database import get_pool, close_pool
    try:
        await get_pool()
        return await coro
    finally:
        await close_pool()
```

Each command wraps its async logic: `asyncio.run(run_with_db(_stats(...)))`.

### 1.9 API key authentication

The TS CLI reads `MANTECATO_API_KEY` and uses it for CRUD operations. The Python CLI should:
- Read from env var `MANTECATO_API_KEY`
- For read-only queries (stats, pages, etc.): connect directly to DB, no auth needed
- For CRUD (annotations, dashboards, saved views): validate the API key against the `api_key` table before proceeding

This matches the TS behavior.

---

## Phase 2: MCP Server Migration

### 2.1 Choose MCP SDK

Use the official Python MCP SDK: `mcp` (PyPI package).

Add to `backend/pyproject.toml`:
```toml
dependencies = [
    ...
    "mcp>=1.0",
]
```

### 2.2 Create `backend/app/mcp/server.py`

Structure:
```python
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("mantecato")

@server.tool()
async def get_stats(site: str, period: str = "30d", ...) -> str:
    # resolve site, dates, run query, return JSON
    ...

@server.tool()
async def get_pages(site: str, period: str = "30d", ...) -> str:
    ...

# ... 41 tools total

async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
```

### 2.3 Tool-by-tool mapping

All 41 MCP tools map 1:1 to the same Python query modules as the CLI. The MCP tools are simpler — they take parameters, run a query, return JSON. No formatting needed.

| MCP Tool | Python query | Notes |
|---|---|---|
| `list_sites` | Direct SQL | |
| `get_stats` | `queries/stats.py` → `get_website_stats()` | |
| `get_timeseries` | `queries/stats.py` → `get_pageview_time_series()` | |
| `get_comparison` | `queries/compare.py` → `get_comparison()` | |
| `get_pages` | `queries/pageviews.py` → `get_page_metrics()` | |
| `get_page_detail` | `queries/pageviews.py` → `get_page_detail()` | |
| `get_top_pages` | `queries/stats.py` → `get_top_pages()` | |
| `get_sources` | `queries/sources.py` → `get_referrer_metrics()` | |
| `get_referrer_pages` | `queries/sources.py` → `get_referrer_page_metrics()` | |
| `get_channels` | `queries/sources.py` → `get_channel_metrics()` | |
| `get_utm` | `queries/sources.py` → `get_utm_metrics()` | |
| `get_click_ids` | `queries/sources.py` → `get_click_id_metrics()` | |
| `get_hostnames` | `queries/sources.py` → `get_hostname_metrics()` | |
| `get_top_referrers` | `queries/stats.py` → `get_top_referrers()` | |
| `get_events` | `queries/events.py` → `get_event_metrics()` | |
| `get_event_detail` | `queries/events.py` → `get_event_time_series()` + `get_event_properties()` | |
| `get_top_events` | `queries/stats.py` → `get_top_events()` | |
| `get_sessions` | `queries/sessions.py` → `get_sessions()` | |
| `get_session_activity` | `queries/sessions.py` → `get_session_activity()` | |
| `get_devices` | `queries/devices.py` → `get_device_breakdown()` | |
| `get_geo` | `queries/geo.py` → `get_geo_breakdown()` | |
| `get_realtime` | `queries/realtime.py` → `get_realtime()` | |
| `get_retention` | `queries/retention.py` → `get_retention()` | |
| `run_funnel` | `queries/funnels.py` → `get_funnel()` | |
| `get_journeys` | `queries/journeys.py` → `get_journeys()` | |
| `get_revenue` | `queries/revenue.py` → various | |
| `get_engagement` | `queries/engagement.py` → `get_engagement()` | |
| `get_filter_values` | `queries/filter_values.py` → `get_filter_values()` | |
| `list_annotations` | `queries/annotations.py` | |
| `create_annotation` | `queries/annotations.py` | |
| `delete_annotation` | `queries/annotations.py` | |
| `list_saved_views` | `queries/saved_views.py` | |
| `get_saved_view` | `queries/saved_views.py` | |
| `create_saved_view` | `queries/saved_views.py` | |
| `delete_saved_view` | `queries/saved_views.py` | |
| `list_dashboards` | `queries/dashboards.py` | |
| `get_dashboard` | `queries/dashboards.py` | |
| `delete_dashboard` | `queries/dashboards.py` | |
| `list_scheduled_exports` | `queries/scheduled_exports.py` | |
| `get_scheduled_export` | `queries/scheduled_exports.py` | |
| `delete_scheduled_export` | `queries/scheduled_exports.py` | |

### 2.4 MCP tool parameters

Each MCP tool in the TS version uses Zod schemas for parameter validation. In Python, use Pydantic models or just type annotations with the `mcp` SDK's built-in validation.

The TS version has these common parameters on most tools:
```typescript
z.object({
  site: z.string(),
  period: z.string().optional().default("30d"),
  start: z.string().optional(),
  end: z.string().optional(),
  filter: z.array(z.string()).optional(),
  limit: z.number().optional().default(20),
  granularity: z.string().optional().default("auto"),
})
```

Python equivalent:
```python
@server.tool()
async def get_stats(
    site: str,
    period: str = "30d",
    start: str | None = None,
    end: str | None = None,
    filter: list[str] | None = None,
    limit: int = 20,
    granularity: str = "auto",
) -> str:
```

### 2.5 MCP config updates

Update `docs/ai-agents.md` and all editor configs:

Before:
```json
{
  "command": "npx",
  "args": ["tsx", "src/mcp/server.ts"]
}
```

After:
```json
{
  "command": "python",
  "args": ["-m", "backend.app.mcp.server"]
}
```

---

## Phase 3: Cleanup

### 3.1 Delete TypeScript source

After both CLI and MCP are verified working in Python:

```bash
rm -rf src/              # CLI, MCP, TS queries, TS lib
rm -rf node_modules/     # if no longer needed for frontend dev
```

Keep `package.json` only if needed for frontend (`npm --prefix frontend`).

### 3.2 Update Prisma dependency

The TS code uses Prisma for:
1. `rawQuery()` via `$queryRawUnsafe` — replaced by `asyncpg` in Python
2. Prisma client generation — only needed if frontend uses it (it doesn't)

Check if anything else depends on Prisma. If not, remove:
```bash
rm -rf prisma/
# Remove prisma from package.json dependencies
```

### 3.3 Update documentation

| File | Changes needed |
|---|---|
| `README.md` | CLI examples: `npm run cli --` → `python -m backend.app.cli.main` or `mantecato` |
| `CLAUDE.md` | Update running instructions, command count |
| `AGENTS.md` | Update architecture description — remove `src/` reference |
| `docs/cli.md` | Update all examples |
| `docs/mcp-server.md` | Update MCP config, all examples |
| `docs/ai-agents.md` | Update all editor configs |
| `docs/docker.md` | Update CLI/MCP Docker profiles |
| `docker-compose.yaml` | Update CLI and MCP service commands |
| `Dockerfile.cli` | Switch from Node to Python |

### 3.4 Update package.json scripts

```json
{
  "scripts": {
    "cli": "python -m backend.app.cli.main",
    "mcp": "python -m backend.app.mcp.server"
  }
}
```

Or remove them entirely if using `pyproject.toml` entry points.

---

## Execution Order

1. **CLI helpers** (`helpers.py`) — port formatting, site resolution, date parsing
2. **CLI main** (`main.py`) — port all 45 commands one by one, test each against TS output
3. **CLI report** (`report.py`) — port the report command with `-H` mode using `rich`
4. **MCP server** (`server.py`) — port all 41 tools
5. **Integration test** — run both Python and TS versions against the same DB, compare outputs
6. **Update docs** — README, CLAUDE.md, AGENTS.md, all docs/
7. **Delete `src/`** — remove TS code, Prisma dependency

## Estimated Scope

| Component | TS Lines | Effort | Notes |
|---|---|---|---|
| CLI helpers | 234 | Low | Most logic already exists in Python backend |
| CLI commands (44) | 800 | Medium | Mechanical — each command is ~15 lines, all query functions exist |
| CLI report | 180 | Medium | Complex formatting, use `rich` |
| MCP server (41 tools) | 1,075 | Medium | Mechanical — same pattern repeated, all query functions exist |
| Docs update | — | Low | Search-and-replace mostly |
| **Total** | 2,289 | | |

The work is largely mechanical because all SQL queries and business logic already exist in `backend/app/queries/`. The migration is really just replacing the TypeScript wrapper (Commander.js + Prisma + formatOutput) with a Python wrapper (Typer + asyncpg + Rich).

## Testing Strategy

For each command, verify output parity:
```bash
# TS version
npx tsx src/cli/index.ts stats -s mysite.com -p 30d -f json > /tmp/ts_output.json

# Python version
python -m backend.app.cli.main stats -s mysite.com -p 30d -f json > /tmp/py_output.json

# Compare
diff /tmp/ts_output.json /tmp/py_output.json
```

JSON output should be identical. Table output may differ in formatting (Rich vs manual) — that's expected and fine.

## Risks

1. **asyncpg connection pool in CLI context** — CLI is short-lived, need to create pool and close it cleanly per invocation. Use a context manager wrapper.
2. **Python MCP SDK maturity** — verify the `mcp` PyPI package supports all needed features (tool registration, stdio transport, parameter validation). Fallback: use `fastmcp` which is more mature.
3. **Prisma removal** — verify nothing in the frontend build depends on Prisma generation. If it does, keep `prisma/` but remove the TS query code.
