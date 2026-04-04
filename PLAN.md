# Mantecato — Evolution Plan

## Vision

Mantecato becomes a complete, modular analytics platform for Umami databases. Four independent, separately installable components that share a common query core:

```
┌─────────────────────────────────────────────────────────┐
│                    Umami PostgreSQL                      │
└─────────┬──────────┬──────────┬──────────┬──────────────┘
          │          │          │          │
     ┌────┴───┐ ┌────┴───┐ ┌───┴────┐ ┌──┴──────────┐
     │ Web UI │ │  CLI   │ │  MCP   │ │   Backend   │
     │ (SPA)  │ │ (PyPI) │ │ (PyPI) │ │   (API)     │
     └────────┘ └────────┘ └────────┘ └─────────────┘
                     │          │          │
                     └──────────┴──────────┘
                        mantecato-core
                     (shared query engine)
```

Plus a companion npm package (`@mantecato/tracker`) as a drop-in Umami-compatible tracker.

## Hard Constraint: Umami Database Compatibility

**Mantecato MUST NOT modify the Umami database schema.** This is non-negotiable.

- Mantecato reads the same PostgreSQL database that Umami writes to. Users run both Umami and Mantecato side by side against the same DB.
- **No migrations.** Mantecato never creates, alters, or drops Umami tables (`website`, `website_event`, `session`, `event_data`).
- **No writes to Umami tables.** Mantecato is read-only against all Umami-owned tables. The only tables Mantecato writes to are its own internal tables (API keys, saved views, dashboards, annotations) which live in a separate `mantecato_` prefixed namespace.
- **Schema follows Umami.** When Umami releases a new version that changes its schema, Mantecato adapts — not the other way around. Queries must work against Umami v2.x schema.
- **The tracker (`@mantecato/tracker`)** sends events in the exact Umami wire format (`POST /api/send`). Events land in the standard Umami tables and are readable by both Umami's UI and Mantecato.
- **If you need new tables** for Mantecato-specific features (saved views, dashboards, scheduled exports, API keys), they MUST use the `mantecato_` prefix and MUST NOT conflict with any Umami table.
- **Test against a real Umami DB.** Every query change must be validated against an actual Umami PostgreSQL instance to ensure compatibility.

Breaking Umami compatibility breaks the entire value proposition. Mantecato is an enhancement layer, not a replacement.

---

## Current State

```
mantecato/
├── frontend/              Vite + React SPA (80 tsx/ts files, 25 deps)
├── backend/
│   └── app/
│       ├── routers/       26 FastAPI routers (1,557 lines)
│       ├── queries/       20 query modules (3,751 lines) ← the core value
│       ├── cli/           45 commands (1,118 lines + 234 helpers + 180 report)
│       ├── mcp/           41 tools (620 lines)
│       ├── database.py    asyncpg pool (108 lines)
│       ├── filters.py     SQL filter builder (172 lines)
│       └── date_utils.py  Date range resolution (177 lines)
├── packages/tracker/      @mantecato/tracker npm package (329 lines)
├── docs/                  5 markdown docs
└── docker-compose.yaml    4 services (frontend, backend, cli, mcp)
```

**Problem**: CLI, MCP, and API are all coupled inside `backend/`. You can't install the CLI without the full FastAPI stack. The MCP server can't be distributed independently. Everything depends on the same `pyproject.toml`.

---

## Target State

```
mantecato/
├── frontend/                  Vite + React SPA (unchanged)
├── backend/                   FastAPI API server (deployable)
│   └── app/
│       ├── routers/
│       └── main.py
├── cli/                       Standalone CLI + TUI (pip install mantecato-cli)
│   ├── pyproject.toml
│   └── mantecato_cli/
│       ├── main.py            Typer app
│       ├── report.py          Report command with -H mode
│       ├── tui.py             Textual TUI dashboard
│       └── config.py          Local config (~/.config/mantecato/)
├── mcp/                       Standalone MCP server (pip install mantecato-mcp)
│   ├── pyproject.toml
│   └── mantecato_mcp/
│       └── server.py
├── core/                      Shared query engine (pip install mantecato-core)
│   ├── pyproject.toml
│   └── mantecato_core/
│       ├── queries/           20 query modules (from backend/app/queries/)
│       ├── database.py        asyncpg pool
│       ├── filters.py         SQL filter builder
│       ├── date_utils.py      Date range resolution
│       └── config.py          DB connection config
├── packages/tracker/          @mantecato/tracker (npm, unchanged)
├── docs/
└── docker-compose.yaml
```

### Dependency graph

```
mantecato-cli  ──depends──→  mantecato-core
mantecato-mcp  ──depends──→  mantecato-core
backend/app    ──depends──→  mantecato-core  (or imports directly during transition)
```

---

## Component Details

### 1. `core/` — mantecato-core (PyPI)

The shared query engine. Everything that talks to the Umami database lives here.

**What moves here from `backend/app/`:**
- `queries/` (all 20 modules, 3,751 lines) — the SQL queries
- `database.py` (108 lines) — asyncpg pool management
- `filters.py` (172 lines) — filter parsing and SQL building
- `date_utils.py` (177 lines) — date range resolution, granularity

**New additions:**
- `config.py` — connection config from env var (`DATABASE_URL`) or config file
- Proper `__init__.py` with clean public API

**pyproject.toml:**
```toml
[project]
name = "mantecato-core"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "asyncpg>=0.30",
]
```

**Public API:**
```python
from mantecato_core import create_pool, close_pool
from mantecato_core.queries import stats, events, pageviews, sources, ...
from mantecato_core.filters import parse_filters, build_filter_sql
from mantecato_core.date_utils import resolve_date_range, resolve_granularity
```

**Key design decisions:**
- Zero web framework dependency — no FastAPI, no Pydantic (queries return plain dicts)
- Async-only API (asyncpg is async)
- The pool is managed by the consumer (CLI creates and destroys per invocation, API keeps it alive)

---

### 2. `cli/` — mantecato-cli (PyPI)

Standalone CLI and TUI. Installable via `pip install mantecato-cli` or `uv tool install mantecato-cli`.

**What moves here from `backend/app/cli/`:**
- `main.py` (1,118 lines) — all 45 Typer commands
- `helpers.py` (234 lines) — output formatting
- `report.py` (180 lines) — report command

**New additions:**

#### Local config (`~/.config/mantecato/config.toml`)
```toml
[database]
url = "postgresql://user:pass@host:5432/umami"

[defaults]
site = "mysite.com"
period = "30d"
format = "table"
```

So users don't need to pass `--site` and `DATABASE_URL` every time. The CLI reads config on startup, env vars override, flags override everything.

#### TUI mode (`mantecato tui`)

A Textual-based terminal UI that shows a live dashboard:
```
┌─ Overview ──────────────────────────────────────────┐
│ Visitors: 7,777 (+132%)  Pageviews: 15,902 (+68%)  │
│ Bounce: 83.6%  Duration: 1m 25s  Pages/Visit: 1.76 │
├─ Traffic ───────────────────────────────────────────┤
│ ▁▂▃▅▆█▇▅▃▄▅▆▇█▆▅▃▂▁▂▃▄▅▆▇██▇▅  (sparkline)      │
├─ Top Pages ────────────┬─ Top Sources ──────────────┤
│ /                  839 │ google.com           1,895 │
│ /content/docs      300 │ duckduckgo.com         534 │
│ /content/examples  201 │ kerykeion.net          316 │
├─ Events ───────────────┴────────────────────────────┤
│ rapidapi_click      45  origin: homepage (30)       │
│ studio_click        38  origin: homepage (25)       │
└─────────────────────────────────────────────────────┘
```

Built with [Textual](https://textual.textualize.io/). Keyboard navigation, period switching, site switching. Refreshes on a configurable interval.

**pyproject.toml:**
```toml
[project]
name = "mantecato-cli"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "mantecato-core>=0.1.0",
    "typer>=0.15",
    "rich>=13.0",
    "textual>=3.0",
]

[project.scripts]
mantecato = "mantecato_cli.main:app"
```

**Usage after install:**
```bash
# Install globally
uv tool install mantecato-cli

# Configure once
mantecato config set database.url "postgresql://..."
mantecato config set defaults.site "mysite.com"

# Use
mantecato report -p 30d -H
mantecato stats
mantecato tui
```

---

### 3. `mcp/` — mantecato-mcp (PyPI)

Standalone MCP server. Installable via `pip install mantecato-mcp` or usable directly.

**What moves here from `backend/app/mcp/`:**
- `server.py` (620 lines) — all 41 tools

**pyproject.toml:**
```toml
[project]
name = "mantecato-mcp"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "mantecato-core>=0.1.0",
    "mcp>=1.0",
]

[project.scripts]
mantecato-mcp = "mantecato_mcp.server:main"
```

**MCP config after install:**
```json
{
  "mcpServers": {
    "mantecato": {
      "command": "mantecato-mcp",
      "env": {
        "DATABASE_URL": "postgresql://..."
      }
    }
  }
}
```

No more `"args": ["python", "-m", "app.mcp.server"]` or `"cwd"` — just a single binary.

**Remote mode (connects to deployed backend instead of direct DB):**
```json
{
  "mcpServers": {
    "mantecato": {
      "command": "mantecato-mcp",
      "env": {
        "MANTECATO_API_URL": "https://mantecato.example.com",
        "MANTECATO_API_KEY": "mtk_..."
      }
    }
  }
}
```

When `MANTECATO_API_URL` is set, the MCP server proxies through the HTTP API instead of connecting to the DB directly. This lets users connect to a deployed Mantecato instance without exposing DB credentials.

---

### 4. `backend/` — Mantecato API server

Stays as FastAPI but imports from `mantecato-core` instead of having its own queries.

**Changes:**
- `app/queries/` → deleted, imports from `mantecato_core.queries`
- `app/database.py` → deleted, imports from `mantecato_core.database`
- `app/filters.py` → deleted, imports from `mantecato_core.filters`
- `app/date_utils.py` → deleted, imports from `mantecato_core.date_utils`
- `app/cli/` → deleted (moved to `cli/`)
- `app/mcp/` → deleted (moved to `mcp/`)
- `app/routers/` → stays, thin wrappers that call core queries
- `app/auth.py`, `app/config.py`, `app/dependencies.py`, `app/main.py` → stays

**pyproject.toml:**
```toml
[project]
name = "mantecato-backend"
dependencies = [
    "mantecato-core>=0.1.0",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "python-jose[cryptography]>=3.3",
    "bcrypt>=4.0",
    "pydantic>=2.10",
    "pydantic-settings>=2.7",
    "python-multipart>=0.0.20",
]
```

---

### 5. `packages/tracker/` — @mantecato/tracker (npm)

Already exists (329 lines). Needs minor improvements:

**Current state:** Umami-compatible tracker with `createTracker()` API and `<script>` tag mode. Sends pageviews and custom events.

**Improvements needed:**
- **Session replay data** — optionally collect click coordinates, scroll depth (Umami-compatible)
- **Revenue tracking** — `tracker.revenue(amount, currency)` that maps to Umami's revenue events
- **React hooks** — `useTracker()`, `usePageview()`, `<TrackerProvider>` for React/Next.js apps
- **SPA router integration** — auto-detect React Router, Next.js App Router, Vue Router for automatic pageview tracking
- **TypeScript-first** — already is, but export stricter types for event names and properties
- **Test suite** — unit tests with vitest, integration tests against a real Umami endpoint
- **README** — proper npm README with usage examples, API reference, comparison with Umami's built-in script

**New sub-package: `@mantecato/tracker-react`** (optional)
```tsx
import { TrackerProvider, useTracker } from '@mantecato/tracker-react';

function App() {
  return (
    <TrackerProvider websiteId="..." baseUrl="...">
      <MyApp />
    </TrackerProvider>
  );
}

function Button() {
  const { event } = useTracker();
  return <button onClick={() => event('click', { target: 'cta' })}>CTA</button>;
}
```

---

## Migration Path

### Phase 1: Extract `core/` (no breaking changes)

1. Create `core/` directory with `pyproject.toml`
2. Copy (not move) `queries/`, `database.py`, `filters.py`, `date_utils.py` from `backend/app/`
3. Make `backend/app/` import from `core/` via path dependency: `mantecato-core = { path = "../core" }`
4. Verify all backend tests pass
5. Verify CLI and MCP still work

**Result:** Same behavior, code lives in two places temporarily.

### Phase 2: Extract `cli/` and `mcp/`

1. Create `cli/` with `pyproject.toml`, depends on `mantecato-core`
2. Move `backend/app/cli/` → `cli/mantecato_cli/`
3. Update imports from `app.queries` → `mantecato_core.queries`
4. Create `mcp/` with `pyproject.toml`, depends on `mantecato-core`
5. Move `backend/app/mcp/` → `mcp/mantecato_mcp/`
6. Update imports
7. Update `docker-compose.yaml` to build from new locations
8. Delete `backend/app/cli/` and `backend/app/mcp/`

**Result:** CLI and MCP are independent packages.

### Phase 3: Delete duplicated code from `backend/`

1. Delete `backend/app/queries/`, `database.py`, `filters.py`, `date_utils.py`
2. `backend/` depends on `mantecato-core` for all query logic
3. Backend is now just routers + auth + config

**Result:** Clean separation. Each package owns its code.

### Phase 4: Add CLI config and TUI

1. Add `mantecato config` commands (get/set/list)
2. Config stored in `~/.config/mantecato/config.toml`
3. Build TUI with Textual
4. Add `mantecato tui` command

### Phase 5: Add MCP remote mode

1. Add HTTP client to `mantecato-mcp` that calls the backend API
2. When `MANTECATO_API_URL` is set, use HTTP instead of direct DB
3. This lets users connect MCP to a deployed instance

### Phase 6: Publish to PyPI

1. Publish `mantecato-core` to PyPI
2. Publish `mantecato-cli` to PyPI
3. Publish `mantecato-mcp` to PyPI
4. Update all docs, README, CLAUDE.md

### Phase 7: Improve `@mantecato/tracker`

1. Add React hooks package
2. Add SPA router integration
3. Add revenue tracking
4. Write tests
5. Publish to npm

---

## File-by-file migration map

### `backend/app/queries/` → `core/mantecato_core/queries/`

| File | Lines | Notes |
|------|-------|-------|
| `stats.py` | 415 | Includes `get_top_events_with_properties` |
| `pageviews.py` | 350 | Page metrics, page detail |
| `sources.py` | 400 | Referrers, channels, UTM, click IDs, hostnames |
| `events.py` | 140 | Event metrics, timeseries, properties |
| `sessions.py` | 280 | Session list, activity replay |
| `devices.py` | 90 | Browser, OS, device, screen, language |
| `geo.py` | 150 | Country, region, city |
| `compare.py` | 80 | Period comparison |
| `retention.py` | 120 | Cohort retention |
| `funnels.py` | 100 | Funnel analysis |
| `journeys.py` | 90 | User journey paths |
| `engagement.py` | 200 | Duration distribution, percentiles |
| `revenue.py` | 180 | Revenue analytics |
| `realtime.py` | 80 | Live visitors |
| `filter_values.py` | 60 | Autocomplete values |
| `annotations.py` | 120 | CRUD |
| `saved_views.py` | 150 | CRUD |
| `dashboards.py` | 200 | CRUD |
| `scheduled_exports.py` | 130 | CRUD |
| `api_keys.py` | 80 | Key management |

### `backend/app/cli/` → `cli/mantecato_cli/`

| File | Lines | Changes needed |
|------|-------|----------------|
| `main.py` | 1,118 | `from app.queries` → `from mantecato_core.queries` |
| `helpers.py` | 234 | `from app.database` → `from mantecato_core.database` |
| `report.py` | 180 | Same import changes |

### `backend/app/mcp/` → `mcp/mantecato_mcp/`

| File | Lines | Changes needed |
|------|-------|----------------|
| `server.py` | 620 | Same import changes + add remote HTTP mode |

---

## New `docker-compose.yaml`

```yaml
services:
  frontend:
    build: ./frontend
    ports: ["${FRONTEND_PORT:-4180}:80"]
    depends_on: [backend]

  backend:
    build: ./backend
    ports: ["${BACKEND_PORT:-8100}:8100"]
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - SESSION_SECRET=${SESSION_SECRET:-mantecato-secret}

  cli:
    build:
      context: .
      dockerfile: cli/Dockerfile
    profiles: ["cli"]
    environment:
      - DATABASE_URL=${DATABASE_URL}
    entrypoint: ["mantecato"]

  mcp:
    build:
      context: .
      dockerfile: mcp/Dockerfile
    profiles: ["mcp"]
    environment:
      - DATABASE_URL=${DATABASE_URL}
    entrypoint: ["mantecato-mcp"]
    stdin_open: true
```

---

## PyPI package names

| Package | Name | Binary | Description |
|---------|------|--------|-------------|
| `core/` | `mantecato-core` | — | Shared Umami query engine |
| `cli/` | `mantecato-cli` | `mantecato` | CLI + TUI |
| `mcp/` | `mantecato-mcp` | `mantecato-mcp` | MCP server |

## npm package names

| Package | Name | Description |
|---------|------|-------------|
| `packages/tracker/` | `@mantecato/tracker` | Umami-compatible tracker |
| `packages/tracker-react/` | `@mantecato/tracker-react` | React hooks + provider |

---

## Definition of Done

- [ ] `uv tool install mantecato-cli` works, `mantecato report -s mysite.com -p 30d -H` runs
- [ ] `mantecato tui` shows a live terminal dashboard
- [ ] `mantecato config set database.url "..."` persists to `~/.config/mantecato/config.toml`
- [ ] `pip install mantecato-mcp` works, `mantecato-mcp` starts MCP server via stdio
- [ ] MCP works both in direct-DB mode and remote-API mode
- [ ] `@mantecato/tracker` published on npm with full Umami compatibility
- [ ] `@mantecato/tracker-react` published with hooks and provider
- [ ] Backend imports from `mantecato-core`, no duplicated query code
- [ ] All 45 CLI commands work identically to current behavior
- [ ] All 41 MCP tools work identically
- [ ] Docker Compose works with new structure
- [ ] README, CLAUDE.md, docs/ all updated
