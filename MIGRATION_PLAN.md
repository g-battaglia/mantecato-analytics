# Mantecato: Next.js → Vite + FastAPI Migration Plan

## Overview

Migrate Mantecato from a Next.js 16 monolith to a **Vite (React SPA)** frontend + **FastAPI (Python)** backend, while keeping the PostgreSQL database schema **100% untouched** and backward-compatible with the existing Umami instance.

### Current Architecture

```
Next.js 16 Monolith
├── React 19 frontend (App Router, server + client components)
├── 28 API route handlers (Node.js, under src/app/api/)
├── 20 SQL query modules (Prisma raw queries, under src/queries/)
├── JWT auth + API key auth (jose + bcryptjs)
├── CLI (Commander.js, 38 commands, under src/cli/)
├── MCP Server (41 tools, under src/mcp/)
├── Zustand state + TanStack React Query
└── PostgreSQL via Prisma (read-heavy, writes only to `report` table)
```

### Target Architecture

```
├── frontend/                    # Vite + React 19 SPA
│   ├── src/
│   │   ├── components/          # Migrated from src/components/
│   │   ├── hooks/               # Migrated from src/hooks/
│   │   ├── stores/              # Migrated from src/stores/
│   │   ├── lib/                 # Client-only utils (date.ts, format.ts, constants.ts, theme.tsx, utils.ts)
│   │   ├── pages/               # Route components (from src/app/(dashboard)/ and src/app/login/)
│   │   ├── router.tsx           # React Router v7 route definitions
│   │   ├── main.tsx             # Entry point
│   │   └── index.css            # Migrated from globals.css
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── package.json
│
├── backend/                     # FastAPI (Python)
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, middleware
│   │   ├── config.py            # Settings (DATABASE_URL, SESSION_SECRET, etc.)
│   │   ├── database.py          # asyncpg connection pool
│   │   ├── auth.py              # JWT sessions + API key validation
│   │   ├── dependencies.py      # FastAPI dependencies (get_current_user, etc.)
│   │   ├── queries/             # Ported from src/queries/ (20 modules)
│   │   │   ├── stats.py
│   │   │   ├── pageviews.py
│   │   │   ├── sources.py
│   │   │   ├── events.py
│   │   │   ├── sessions.py
│   │   │   ├── devices.py
│   │   │   ├── geo.py
│   │   │   ├── realtime.py
│   │   │   ├── compare.py
│   │   │   ├── retention.py
│   │   │   ├── funnels.py
│   │   │   ├── journeys.py
│   │   │   ├── revenue.py
│   │   │   ├── engagement.py
│   │   │   ├── filter_values.py
│   │   │   ├── annotations.py
│   │   │   ├── saved_views.py
│   │   │   ├── dashboards.py
│   │   │   ├── scheduled_exports.py
│   │   │   └── api_keys.py
│   │   ├── routers/             # Ported from src/app/api/ (28 route files)
│   │   │   ├── auth.py
│   │   │   ├── sites.py
│   │   │   ├── stats.py
│   │   │   ├── pages.py
│   │   │   ├── sources.py
│   │   │   ├── events.py
│   │   │   ├── sessions.py
│   │   │   ├── devices.py
│   │   │   ├── geo.py
│   │   │   ├── realtime.py
│   │   │   ├── compare.py
│   │   │   ├── retention.py
│   │   │   ├── funnels.py
│   │   │   ├── journeys.py
│   │   │   ├── revenue.py
│   │   │   ├── engagement.py
│   │   │   ├── filter_values.py
│   │   │   ├── annotations.py
│   │   │   ├── saved_views.py
│   │   │   ├── dashboards.py
│   │   │   ├── scheduled_exports.py
│   │   │   ├── api_keys.py
│   │   │   ├── script.py
│   │   │   ├── share.py
│   │   │   └── cron.py
│   │   ├── models.py            # Pydantic models (request/response schemas)
│   │   └── filters.py           # Filter parsing & SQL builder (from src/lib/queries.ts)
│   ├── requirements.txt
│   ├── pyproject.toml
│   └── Dockerfile
│
├── src/cli/                     # UNCHANGED — keeps running via tsx
├── src/mcp/                     # UNCHANGED — keeps running via tsx
├── prisma/schema.prisma         # UNCHANGED — kept for CLI/MCP and as schema reference
├── docker-compose.yaml          # Updated: web → frontend + backend services
└── CLAUDE.md                    # Updated
```

---

## Guiding Principles

1. **Database is sacred.** Zero schema changes. No migrations. No new tables. No column changes. All existing SQL queries must produce identical results.
2. **API contract preserved.** Every endpoint must accept the same query parameters and return the same JSON shape. The frontend should not need to adapt to API changes — it's a 1:1 port.
3. **CLI and MCP untouched.** They connect directly to the DB via Prisma/tsx. They don't use Next.js API routes. Leave them as-is.
4. **Incremental verification.** Each phase should be testable independently before moving to the next.

---

## Phase 0: Pre-Migration Setup

### 0.1 Create directory structure

```bash
mkdir -p frontend/src/{components,hooks,stores,lib,pages}
mkdir -p frontend/public
mkdir -p backend/app/{queries,routers}
```

### 0.2 Initialize Vite project

```bash
cd frontend
npm create vite@latest . -- --template react-ts
```

**`frontend/package.json`** dependencies (carry over from current):
```json
{
  "dependencies": {
    "@hello-pangea/dnd": "^18.0.1",
    "@tanstack/react-query": "^5.91.3",
    "@tanstack/react-table": "^8.21.3",
    "@tanstack/react-virtual": "^3.13.23",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "d3-sankey": "^0.12.3",
    "date-fns": "^4.1.0",
    "html2canvas": "^1.4.1",
    "jspdf": "^4.2.1",
    "lucide-react": "^0.577.0",
    "radix-ui": "^1.4.3",
    "react": "^19.2.4",
    "react-day-picker": "^9.14.0",
    "react-dom": "^19.2.4",
    "react-router": "^7.6.0",
    "react-simple-maps": "^3.0.0",
    "recharts": "^3.8.0",
    "tailwind-merge": "^3.5.0",
    "tw-animate-css": "^1.4.0",
    "xlsx": "^0.18.5",
    "zod": "^4.3.6",
    "zustand": "^5.0.12"
  },
  "devDependencies": {
    "@tailwindcss/vite": "^4",
    "@types/d3-sankey": "^0.12.5",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "tailwindcss": "^4",
    "typescript": "^5",
    "vite": "^6"
  }
}
```

Note: `shadcn` is NOT a runtime dependency — the generated component files in `src/components/ui/` are self-contained. Copy them over. No shadcn CLI needed at runtime.

**`frontend/vite.config.ts`:**
```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      // Replicate Turbopack alias for fflate
      fflate: "fflate/browser",
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
```

**`frontend/tsconfig.json`:**
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["dom", "dom.iterable", "esnext"],
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "react-jsx",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"]
}
```

### 0.3 Initialize FastAPI project

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
```

**`backend/requirements.txt`:**
```
fastapi>=0.115
uvicorn[standard]>=0.34
asyncpg>=0.30
python-jose[cryptography]>=3.3
passlib[bcrypt]>=1.7
pydantic>=2.10
pydantic-settings>=2.7
python-multipart>=0.0.20
```

**`backend/pyproject.toml`:**
```toml
[project]
name = "mantecato-backend"
version = "0.1.0"
requires-python = ">=3.12"
```

---

## Phase 1: Backend (FastAPI)

This is the critical path. The backend must be fully functional before the frontend can be tested.

### 1.1 Database connection (`backend/app/database.py`)

Use **asyncpg** directly (no ORM). The current codebase uses raw SQL via Prisma's `$queryRawUnsafe` — asyncpg is a natural fit.

```python
import asyncpg
from .config import settings

pool: asyncpg.Pool | None = None

async def get_pool() -> asyncpg.Pool:
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(settings.DATABASE_URL)
    return pool

async def raw_query(sql: str, params: dict | None = None) -> list[dict]:
    """
    Execute raw SQL with named parameter substitution.
    Converts {{name}} and {{name::type}} syntax to $1, $2::type etc.
    Must be 1:1 compatible with the current rawQuery() in src/lib/queries.ts.
    """
    ...
```

**Key requirement:** The `raw_query()` function must replicate the exact parameter substitution logic from `src/lib/queries.ts`:
- `{{name}}` → `$N`
- `{{name::uuid}}` → `$N::uuid`
- Parameters collected in order of appearance

Also port `pagedRawQuery`, `getDateTrunc`, `buildFilterSQL`, `parseFiltersFromParams`, and `applyFilters`.

### 1.2 Configuration (`backend/app/config.py`)

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    SESSION_SECRET: str = "mantecato-default-secret"
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]  # Vite dev

    class Config:
        env_file = "../.env"
```

### 1.3 Authentication (`backend/app/auth.py`)

Port `src/lib/auth.ts` to Python:

| TypeScript (current) | Python (target) |
|---|---|
| `jose` (HS256 JWT) | `python-jose` (HS256 JWT) |
| `bcryptjs.compare()` | `passlib.hash.bcrypt.verify()` |
| `cookies()` from next/headers | FastAPI `Response.set_cookie()` / `Request.cookies` |
| Cookie name: `mantecato-session` | **Same cookie name** |
| Max age: 7 days | **Same** |
| Payload: `{ userId, username, role }` | **Same JWT payload structure** |

**Critical:** The JWT tokens must be cross-compatible. Both jose (JS) and python-jose use standard HS256 JWT. As long as the same `SESSION_SECRET` is used, tokens created by either implementation will validate in the other. This means existing sessions survive the migration.

Also port API key validation from `src/queries/api-keys.ts`:
- SHA-256 hash lookup via `report.parameters->>'keyHash'`
- Scope checking ("read", "write")

### 1.4 Dependencies (`backend/app/dependencies.py`)

```python
from fastapi import Depends, Cookie, HTTPException

async def get_current_user(mantecato_session: str | None = Cookie(None, alias="mantecato-session")):
    """Validates JWT from cookie. Returns SessionPayload or raises 401."""
    ...

async def require_site_access(site_id: str, user = Depends(get_current_user)):
    """Checks canAccessWebsite(). Raises 403 if no access."""
    ...
```

### 1.5 Port query modules (`backend/app/queries/`)

Port each of the 20 query modules from `src/queries/*.ts`. These are the source files:

| Source (TypeScript) | Target (Python) | Functions |
|---|---|---|
| `src/queries/stats.ts` | `queries/stats.py` | `getWebsiteStats`, `getPageviewTimeSeries`, `getTopPages`, `getTopReferrers`, `getTopEvents`, `getDeviceBreakdown`, `getCountryBreakdown` |
| `src/queries/pageviews.ts` | `queries/pageviews.py` | `getPageMetrics`, `getPageReferrers`, `getNextPages`, `getTimeOnPageDistribution`, `getPageTimeSeries` |
| `src/queries/sources.ts` | `queries/sources.py` | `getReferrerMetrics`, `getUTMDetailMetrics`, `getChannelMetrics`, `getClickIdMetrics`, `getHostnameMetrics`, `getReferrerPages` |
| `src/queries/events.ts` | `queries/events.py` | `getEventMetrics`, `getEventTimeSeries`, `getEventProperties` |
| `src/queries/sessions.ts` | `queries/sessions.py` | `getSessionList`, `getSessionActivity` |
| `src/queries/devices.ts` | `queries/devices.py` | `getDeviceMetrics` |
| `src/queries/geo.ts` | `queries/geo.py` | `getGeoMetrics` |
| `src/queries/realtime.ts` | `queries/realtime.py` | `getActiveVisitors`, `getRecentEvents`, `getCurrentPages` |
| `src/queries/compare.ts` | `queries/compare.py` | `getComparisonStats` |
| `src/queries/retention.ts` | `queries/retention.py` | `getRetention` |
| `src/queries/funnels.ts` | `queries/funnels.py` | `getFunnel` |
| `src/queries/journeys.ts` | `queries/journeys.py` | `getJourneys` |
| `src/queries/revenue.ts` | `queries/revenue.py` | `getRevenueSummary`, `getRevenueTimeSeries`, `getRevenueByEvent`, `getRevenueByCountry` |
| `src/queries/engagement.ts` | `queries/engagement.py` | `getDurationDistribution`, `getDurationPercentiles`, `getDurationByPage`, `getBounceRateByPage`, `getBounceRateBySource` |
| `src/queries/filter-values.ts` | `queries/filter_values.py` | `getFilterValues` |
| `src/queries/annotations.ts` | `queries/annotations.py` | `listAnnotations`, `createAnnotation`, `deleteAnnotation` |
| `src/queries/saved-views.ts` | `queries/saved_views.py` | `listSavedViews`, `getSavedView`, `createSavedView`, `deleteSavedView` |
| `src/queries/dashboards.ts` | `queries/dashboards.py` | `listDashboards`, `getDashboard`, `deleteDashboard` |
| `src/queries/scheduled-exports.ts` | `queries/scheduled_exports.py` | `listScheduledExports`, `getScheduledExport`, `deleteScheduledExport` |
| `src/queries/api-keys.ts` | `queries/api_keys.py` | `listApiKeys`, `createApiKey`, `deleteApiKey`, `validateApiKey` |

**Porting rules:**
- Each function uses `rawQuery()` with the **exact same SQL strings**. Copy the SQL verbatim.
- The `{{param}}` / `{{param::type}}` syntax is handled by the shared `raw_query()` function in `database.py`.
- Return types: use Python dicts. The API router will serialize to JSON via Pydantic or `jsonable_encoder`.
- `bigint` values from PostgreSQL: asyncpg returns Python `int`. The current JS code sometimes returns `BigInt` which gets serialized as number — ensure parity.
- `Decimal` values: asyncpg returns `decimal.Decimal`. Serialize as `float` to match the current JSON output.

### 1.6 Port API routes (`backend/app/routers/`)

Port each of the 28 API route files. Preserve **exact same URL paths and HTTP methods**.

| Source (Next.js route) | Target (FastAPI router) | Methods |
|---|---|---|
| `api/auth/route.ts` | `routers/auth.py` | `POST /api/auth`, `DELETE /api/auth` |
| `api/sites/route.ts` | `routers/sites.py` | `GET /api/sites` |
| `api/sites/[siteId]/stats/route.ts` | `routers/stats.py` | `GET /api/sites/{site_id}/stats` |
| `api/sites/[siteId]/pages/route.ts` | `routers/pages.py` | `GET /api/sites/{site_id}/pages` |
| `api/sites/[siteId]/sources/route.ts` | `routers/sources.py` | `GET /api/sites/{site_id}/sources` |
| `api/sites/[siteId]/events/route.ts` | `routers/events.py` | `GET /api/sites/{site_id}/events` |
| `api/sites/[siteId]/sessions/route.ts` | `routers/sessions.py` | `GET /api/sites/{site_id}/sessions` |
| `api/sites/[siteId]/devices/route.ts` | `routers/devices.py` | `GET /api/sites/{site_id}/devices` |
| `api/sites/[siteId]/geo/route.ts` | `routers/geo.py` | `GET /api/sites/{site_id}/geo` |
| `api/sites/[siteId]/realtime/route.ts` | `routers/realtime.py` | `GET /api/sites/{site_id}/realtime` |
| `api/sites/[siteId]/compare/route.ts` | `routers/compare.py` | `GET /api/sites/{site_id}/compare` |
| `api/sites/[siteId]/retention/route.ts` | `routers/retention.py` | `GET /api/sites/{site_id}/retention` |
| `api/sites/[siteId]/funnels/route.ts` | `routers/funnels.py` | `GET /api/sites/{site_id}/funnels` |
| `api/sites/[siteId]/journeys/route.ts` | `routers/journeys.py` | `GET /api/sites/{site_id}/journeys` |
| `api/sites/[siteId]/revenue/route.ts` | `routers/revenue.py` | `GET /api/sites/{site_id}/revenue` |
| `api/sites/[siteId]/engagement/route.ts` | `routers/engagement.py` | `GET /api/sites/{site_id}/engagement` |
| `api/sites/[siteId]/filter-values/route.ts` | `routers/filter_values.py` | `GET /api/sites/{site_id}/filter-values` |
| `api/sites/[siteId]/annotations/route.ts` | `routers/annotations.py` | `GET/POST /api/sites/{site_id}/annotations` |
| `api/sites/[siteId]/saved-views/route.ts` | `routers/saved_views.py` | `GET/POST /api/sites/{site_id}/saved-views` |
| `api/sites/[siteId]/saved-views/[viewId]/route.ts` | `routers/saved_views.py` | `GET/PUT/DELETE /api/sites/{site_id}/saved-views/{view_id}` |
| `api/dashboards/route.ts` | `routers/dashboards.py` | `GET/POST /api/dashboards` |
| `api/dashboards/[dashboardId]/route.ts` | `routers/dashboards.py` | `GET/PUT/DELETE /api/dashboards/{dashboard_id}` |
| `api/scheduled-exports/route.ts` | `routers/scheduled_exports.py` | `GET/POST /api/scheduled-exports` |
| `api/scheduled-exports/[exportId]/route.ts` | `routers/scheduled_exports.py` | `GET/PUT/DELETE /api/scheduled-exports/{export_id}` |
| `api/cron/exports/route.ts` | `routers/cron.py` | `POST /api/cron/exports` |
| `api/api-keys/route.ts` | `routers/api_keys.py` | `GET/POST/DELETE /api/api-keys` |
| `api/script/route.ts` | `routers/script.py` | `POST /api/script` |
| `api/share/[shareId]/stats/route.ts` | `routers/share.py` | `GET /api/share/{share_id}/stats` |

**Porting pattern for each route:**

```python
# Example: routers/stats.py
from fastapi import APIRouter, Depends, Query
from ..dependencies import require_site_access
from ..queries.stats import (
    get_website_stats, get_pageview_time_series,
    get_top_pages, get_top_referrers, get_top_events,
    get_device_breakdown, get_country_breakdown,
)
from ..filters import parse_filters_from_params
from ..auth import SessionPayload

router = APIRouter()

@router.get("/api/sites/{site_id}/stats")
async def get_stats(
    site_id: str,
    user: SessionPayload = Depends(require_site_access),
    range: str = "30d",
    start: str | None = None,
    end: str | None = None,
    granularity: str = "day",
    section: str | None = None,
    f: list[str] = Query(default=[]),  # filter params
):
    filters = parse_filters(f)
    # ... same logic as current route.ts
```

### 1.7 FastAPI app assembly (`backend/app/main.py`)

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .database import get_pool
from .config import settings
from .routers import (
    auth, sites, stats, pages, sources, events, sessions,
    devices, geo, realtime, compare, retention, funnels,
    journeys, revenue, engagement, filter_values, annotations,
    saved_views, dashboards, scheduled_exports, api_keys,
    script, share, cron,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()  # Initialize connection pool
    yield
    pool = await get_pool()
    await pool.close()

app = FastAPI(title="Mantecato API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,  # Required for cookie auth
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routers
for router_module in [
    auth, sites, stats, pages, sources, events, sessions,
    devices, geo, realtime, compare, retention, funnels,
    journeys, revenue, engagement, filter_values, annotations,
    saved_views, dashboards, scheduled_exports, api_keys,
    script, share, cron,
]:
    app.include_router(router_module.router)
```

### 1.8 Filter system (`backend/app/filters.py`)

Port the entire filter system from `src/lib/queries.ts`:
- `Filter` dataclass with `column`, `operator`, `value`
- `VALID_FILTER_COLUMNS` whitelist (same 18 columns)
- `SESSION_COLUMNS` list (same 8 columns)
- `build_filter_sql()` — same grouping logic (OR within column, AND across columns)
- `parse_filters_from_params()` — parse `f=column:operator:value` format
- `apply_filters()` — returns `where`, `params`, `join`

### 1.9 Date utilities (`backend/app/date_utils.py`)

Port from `src/lib/date.ts`:
- `resolve_date_range(preset)` — all 22 presets (1h, 3h, 6h, today, yesterday, 24h, 7d, 14d, 30d, 60d, 90d, 6m, 12m, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, all)
- `resolve_granularity(granularity, range)` — auto-resolution logic
- `get_comparison_range(range, mode)` — previous_period, previous_year, custom

---

## Phase 2: Frontend (Vite + React)

### 2.1 Copy shared client code as-is

These files are already client-side only and need minimal changes:

| Source | Target | Changes needed |
|---|---|---|
| `src/components/ui/*.tsx` (18 files) | `frontend/src/components/ui/` | None — shadcn components are self-contained |
| `src/components/charts/*.tsx` (6 files) | `frontend/src/components/charts/` | None |
| `src/components/data/*.tsx` (2 files) | `frontend/src/components/data/` | None |
| `src/components/filters/*.tsx` (4 files) | `frontend/src/components/filters/` | None |
| `src/components/annotations/*.tsx` | `frontend/src/components/annotations/` | None |
| `src/components/dashboard/*.tsx` | `frontend/src/components/dashboard/` | None |
| `src/components/export/*.tsx` | `frontend/src/components/export/` | None |
| `src/components/layout/*.tsx` (3 files) | `frontend/src/components/layout/` | Replace `next/navigation` imports (see 2.3) |
| `src/components/providers.tsx` | `frontend/src/components/providers.tsx` | Remove server-component theme init (see 2.4) |
| `src/stores/filters.ts` | `frontend/src/stores/filters.ts` | None |
| `src/stores/preferences.ts` | `frontend/src/stores/preferences.ts` | None |
| `src/hooks/use-mobile.ts` | `frontend/src/hooks/use-mobile.ts` | None |
| `src/hooks/use-url-state.ts` | `frontend/src/hooks/use-url-state.ts` | None |
| `src/lib/constants.ts` | `frontend/src/lib/constants.ts` | None |
| `src/lib/date.ts` | `frontend/src/lib/date.ts` | None |
| `src/lib/format.ts` | `frontend/src/lib/format.ts` | None |
| `src/lib/utils.ts` | `frontend/src/lib/utils.ts` | None |
| `src/lib/theme.tsx` | `frontend/src/lib/theme.tsx` | None (already client-side context) |
| `src/lib/dashboard-types.ts` | `frontend/src/lib/dashboard-types.ts` | None |
| `src/lib/export.ts` | `frontend/src/lib/export.ts` | None |
| `src/lib/export-visual.ts` | `frontend/src/lib/export-visual.ts` | None |
| `src/app/globals.css` | `frontend/src/index.css` | None (Tailwind v4 with @import works in Vite) |
| `public/*` | `frontend/public/` | None |
| `src/types/*.d.ts` | `frontend/src/types/` | None |

Files **NOT** to copy to frontend (backend-only):
- `src/lib/auth.ts` — uses `next/headers` cookies, server-only
- `src/lib/prisma.ts` — server-only database client
- `src/lib/queries.ts` — server-only SQL execution (filter parsing already ported to backend)
- `src/queries/*` — server-only SQL modules
- `src/app/api/*` — API routes → FastAPI

### 2.2 `components.json` (shadcn config)

Copy `components.json` to `frontend/` and update the `tailwind.css` path:

```json
{
  "style": "default",
  "tailwind": {
    "css": "src/index.css"
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils"
  }
}
```

### 2.3 Replace Next.js navigation with React Router

All Next.js-specific imports must be replaced:

| Next.js import | React Router replacement |
|---|---|
| `import { useRouter } from "next/navigation"` | `import { useNavigate } from "react-router"` |
| `import { useParams } from "next/navigation"` | `import { useParams } from "react-router"` |
| `import { useSearchParams } from "next/navigation"` | `import { useSearchParams } from "react-router"` |
| `import { usePathname } from "next/navigation"` | `import { useLocation } from "react-router"` → `location.pathname` |
| `import Link from "next/link"` | `import { Link } from "react-router"` |
| `import { redirect } from "next/navigation"` | `import { Navigate } from "react-router"` (component) or `useNavigate()` (hook) |
| `router.push("/path")` | `navigate("/path")` |
| `router.replace("/path")` | `navigate("/path", { replace: true })` |

**`useSiteQuery` hook** (`frontend/src/hooks/use-site-query.ts`):
- Replace `useParams` import from `next/navigation` → `react-router`
- Everything else stays the same

### 2.4 Replace Next.js server-component patterns

The current `src/app/layout.tsx` is a **server component** that reads cookies to resolve the theme. In Vite (all client-side), this changes:

**Root layout → `frontend/src/main.tsx`:**
```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { Providers } from "@/components/providers";
import { AppRouter } from "@/router";
import "@/index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Providers>
        <AppRouter />
      </Providers>
    </BrowserRouter>
  </StrictMode>
);
```

**`frontend/index.html`:**
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Mantecato</title>
    <link rel="icon" href="/favicon.ico" />
    <!-- Inline script to prevent FOUC (flash of unstyled content) -->
    <script>
      (function() {
        const theme = document.cookie.match(/theme=(light|dark)/)?.[1] || "dark";
        document.documentElement.classList.add(theme);
      })();
    </script>
  </head>
  <body class="min-h-svh bg-background text-foreground antialiased">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

**Fonts:** Replace `next/font/google` with direct `<link>` tags in `index.html` or a CSS `@import`:
```css
/* Add to index.css */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@100..900&family=JetBrains+Mono:wght@100..800&display=swap');
```

Then set the CSS variables:
```css
:root {
  --font-sans: 'Inter', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
}
```

### 2.5 Routing (`frontend/src/router.tsx`)

Map the current Next.js App Router structure to React Router:

```tsx
import { Routes, Route, Navigate } from "react-router";
import { DashboardLayout } from "@/pages/dashboard/layout";
import { LoginPage } from "@/pages/login";
import { SharePage } from "@/pages/share";

// Dashboard pages
import { HomePage } from "@/pages/dashboard/home";
import { OverviewPage } from "@/pages/dashboard/sites/overview";
import { PagesPage } from "@/pages/dashboard/sites/pages";
import { SourcesPage } from "@/pages/dashboard/sites/sources";
import { EventsPage } from "@/pages/dashboard/sites/events";
import { SessionsPage } from "@/pages/dashboard/sites/sessions";
import { DevicesPage } from "@/pages/dashboard/sites/devices";
import { GeoPage } from "@/pages/dashboard/sites/geo";
import { RealtimePage } from "@/pages/dashboard/sites/realtime";
import { ComparePage } from "@/pages/dashboard/sites/compare";
import { RetentionPage } from "@/pages/dashboard/sites/retention";
import { FunnelsPage } from "@/pages/dashboard/sites/funnels";
import { JourneysPage } from "@/pages/dashboard/sites/journeys";
import { EngagementPage } from "@/pages/dashboard/sites/engagement";
import { RevenuePage } from "@/pages/dashboard/sites/revenue";
import { DashboardsPage } from "@/pages/dashboard/dashboards";
import { DashboardDetailPage } from "@/pages/dashboard/dashboards/detail";
import { SettingsPage } from "@/pages/dashboard/settings";

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/share/:shareId" element={<SharePage />} />

      {/* Protected dashboard routes */}
      <Route element={<DashboardLayout />}>
        <Route index element={<HomePage />} />
        <Route path="sites/:siteId" element={<OverviewPage />} />
        <Route path="sites/:siteId/pages" element={<PagesPage />} />
        <Route path="sites/:siteId/sources" element={<SourcesPage />} />
        <Route path="sites/:siteId/events" element={<EventsPage />} />
        <Route path="sites/:siteId/sessions" element={<SessionsPage />} />
        <Route path="sites/:siteId/devices" element={<DevicesPage />} />
        <Route path="sites/:siteId/geo" element={<GeoPage />} />
        <Route path="sites/:siteId/realtime" element={<RealtimePage />} />
        <Route path="sites/:siteId/compare" element={<ComparePage />} />
        <Route path="sites/:siteId/retention" element={<RetentionPage />} />
        <Route path="sites/:siteId/funnels" element={<FunnelsPage />} />
        <Route path="sites/:siteId/journeys" element={<JourneysPage />} />
        <Route path="sites/:siteId/engagement" element={<EngagementPage />} />
        <Route path="sites/:siteId/revenue" element={<RevenuePage />} />
        <Route path="dashboards" element={<DashboardsPage />} />
        <Route path="dashboards/:dashboardId" element={<DashboardDetailPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
```

### 2.6 Dashboard layout (`frontend/src/pages/dashboard/layout.tsx`)

Replace the server-component layout with a client-side auth guard:

```tsx
import { Outlet, Navigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/layout/AppSidebar";

export function DashboardLayout() {
  // Check auth status by hitting a lightweight endpoint
  const { data, isLoading, isError } = useQuery({
    queryKey: ["auth-check"],
    queryFn: async () => {
      const res = await fetch("/api/sites");
      if (res.status === 401) throw new Error("unauthorized");
      return res.json();
    },
    retry: false,
  });

  if (isLoading) return null; // or a loading skeleton
  if (isError) return <Navigate to="/login" replace />;

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <Outlet />
      </SidebarInset>
    </SidebarProvider>
  );
}
```

### 2.7 Page components

Each page under `src/app/(dashboard)/sites/[siteId]/*/page.tsx` maps to a page component. These are already `"use client"` components in the current codebase, so the migration is mostly:

1. Remove `"use client"` directive (not needed in Vite — everything is client)
2. Replace `next/navigation` imports with `react-router` equivalents
3. Remove any `redirect()` calls from server-component sections — replace with `<Navigate>` or `useNavigate()`

The page components themselves (data fetching via `useSiteQuery`, rendering charts, tables, etc.) stay identical.

### 2.8 Login page (`frontend/src/pages/login.tsx`)

Port `src/app/login/page.tsx`. The login form already uses `fetch("/api/auth", { method: "POST" })` — this stays the same. Just replace `router.push("/")` with `navigate("/")`.

---

## Phase 3: Remove Next.js-specific code

### 3.1 Files to delete

After Phases 1 and 2 are complete and tested:

```
# Next.js specific
src/app/                         # All pages and API routes (replaced by frontend/ + backend/)
next.config.ts                   # No longer needed
next-env.d.ts                    # No longer needed
postcss.config.mjs               # Tailwind is now in Vite plugin
middleware.ts                     # If it exists

# Server-only libs (now in FastAPI)
src/lib/auth.ts                  # → backend/app/auth.py
src/lib/prisma.ts                # → backend/app/database.py
src/lib/queries.ts               # → backend/app/database.py + filters.py
src/queries/                     # → backend/app/queries/

# Client-only libs (now in frontend/)
src/components/                  # → frontend/src/components/
src/hooks/                       # → frontend/src/hooks/
src/stores/                      # → frontend/src/stores/
src/lib/constants.ts             # → frontend/src/lib/constants.ts
src/lib/date.ts                  # → frontend/src/lib/date.ts
src/lib/format.ts                # → frontend/src/lib/format.ts
src/lib/utils.ts                 # → frontend/src/lib/utils.ts
src/lib/theme.tsx                # → frontend/src/lib/theme.tsx
src/lib/dashboard-types.ts       # → frontend/src/lib/dashboard-types.ts
src/lib/export.ts                # → frontend/src/lib/export.ts
src/lib/export-visual.ts         # → frontend/src/lib/export-visual.ts
src/types/                       # → frontend/src/types/
public/                          # → frontend/public/
```

### 3.2 Files to keep

```
src/cli/                         # Untouched — still uses tsx + Prisma
src/mcp/                         # Untouched — still uses tsx + Prisma
src/generated/prisma/            # Still needed by CLI/MCP
src/lib/prisma.ts                # Still needed by CLI/MCP (keep as src/lib/prisma.ts)
src/lib/queries.ts               # Still needed by CLI/MCP
src/lib/auth.ts                  # Still needed by CLI (API key validation uses some of this)
src/lib/date.ts                  # Still needed by CLI (date parsing)
src/lib/constants.ts             # Still needed by CLI (presets, filter columns)
src/queries/                     # Still needed by CLI/MCP

prisma/schema.prisma             # Schema reference, Prisma generation
```

**IMPORTANT:** Since CLI and MCP import from `src/lib/` and `src/queries/`, these files must remain in place. The `src/` directory is **shared** between CLI/MCP (TypeScript) and the old codebase. Do NOT delete the TypeScript query/lib files — they are the source of truth for the CLI and MCP.

**Revised approach:** Keep the entire `src/` directory intact for CLI/MCP. The frontend and backend are additive — they live in `frontend/` and `backend/` alongside the existing `src/`. Only delete `src/app/` (Next.js pages/routes) and Next.js config files.

### 3.3 Updated files to delete (revised)

```
src/app/                         # Next.js pages and API routes only
next.config.ts
next-env.d.ts
postcss.config.mjs
```

### 3.4 Root `package.json` update

Remove Next.js from root dependencies. Keep the root `package.json` for CLI/MCP:

```json
{
  "name": "mantecato",
  "version": "0.2.0",
  "private": true,
  "license": "MIT",
  "bin": {
    "mantecato": "./src/cli/index.ts"
  },
  "scripts": {
    "dev": "concurrently \"cd frontend && npm run dev\" \"cd backend && uvicorn app.main:app --reload --port 8000\"",
    "dev:frontend": "cd frontend && npm run dev",
    "dev:backend": "cd backend && uvicorn app.main:app --reload --port 8000",
    "build:frontend": "cd frontend && npm run build",
    "cli": "tsx src/cli/index.ts",
    "mcp": "tsx src/mcp/server.ts"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.27.1",
    "@prisma/adapter-pg": "^7.5.0",
    "@prisma/client": "^7.5.0",
    "bcryptjs": "^3.0.3",
    "commander": "^14.0.3",
    "date-fns": "^4.1.0",
    "jose": "^6.2.2",
    "pg": "^8.20.0",
    "prisma": "^7.5.0",
    "zod": "^4.3.6"
  },
  "devDependencies": {
    "@types/node": "^20",
    "@types/pg": "^8.18.0",
    "concurrently": "^9",
    "dotenv": "^17.3.1",
    "tsx": "^4.21.0",
    "typescript": "^5"
  }
}
```

---

## Phase 4: Docker & Deployment

### 4.1 Frontend Dockerfile (`frontend/Dockerfile`)

```dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

**`frontend/nginx.conf`:**
```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy API to backend
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 4.2 Backend Dockerfile (`backend/Dockerfile`)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 4.3 Updated `docker-compose.yaml`

```yaml
services:
  frontend:
    build:
      context: ./frontend
    ports:
      - "${PORT:-3000}:80"
    depends_on:
      - backend
    restart: unless-stopped

  backend:
    build:
      context: ./backend
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - SESSION_SECRET=${SESSION_SECRET:-mantecato-secret}
      - CORS_ORIGINS=["http://localhost:${PORT:-3000}"]
    expose:
      - "8000"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/sites')"]
      interval: 30s
      timeout: 5s
      retries: 3

  cli:
    build:
      context: .
      dockerfile: Dockerfile.cli
    profiles: ["cli"]
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - MANTECATO_API_KEY=${MANTECATO_API_KEY}
    entrypoint: ["npx", "tsx", "src/cli/index.ts"]
    working_dir: /app

  mcp:
    build:
      context: .
      dockerfile: Dockerfile.cli
    profiles: ["mcp"]
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - MANTECATO_API_KEY=${MANTECATO_API_KEY}
    entrypoint: ["npx", "tsx", "src/mcp/server.ts"]
    working_dir: /app
    stdin_open: true
```

---

## Phase 5: Verification Checklist

### 5.1 Backend API parity tests

For each of the 28 endpoints, compare the JSON output from the old Next.js API and the new FastAPI:

```bash
# Start both servers simultaneously
# Old: next dev on port 3000
# New: uvicorn on port 8000

# Login and capture cookies
curl -X POST http://localhost:3000/api/auth -d '{"username":"admin","password":"xxx"}' -c old.cookies
curl -X POST http://localhost:8000/api/auth -d '{"username":"admin","password":"xxx"}' -c new.cookies

# Compare each endpoint
for endpoint in sites "sites/{SITE_ID}/stats" "sites/{SITE_ID}/pages" ...; do
  diff <(curl -s -b old.cookies "http://localhost:3000/api/$endpoint" | jq -S .) \
       <(curl -s -b new.cookies "http://localhost:8000/api/$endpoint" | jq -S .) \
    && echo "✓ $endpoint" || echo "✗ $endpoint"
done
```

### 5.2 Frontend verification

- [ ] All 16 dashboard pages render correctly
- [ ] Login/logout flow works
- [ ] Date range picker and presets work
- [ ] Filters (add, remove, clear) work
- [ ] Theme toggle (light/dark) persists
- [ ] All charts render (Area, Bar, Pie, WorldMap, Sankey)
- [ ] Data tables paginate and sort
- [ ] Real-time page auto-refreshes
- [ ] Export (PDF, PNG, Excel) works
- [ ] Dashboard builder (drag & drop, widget CRUD) works
- [ ] Annotations CRUD works
- [ ] Saved views CRUD works
- [ ] API keys CRUD works
- [ ] Public share pages work
- [ ] Mobile responsive layout works

### 5.3 CLI and MCP verification

- [ ] `npx tsx src/cli/index.ts sites` still works
- [ ] `npx tsx src/cli/index.ts stats --site <site>` returns correct data
- [ ] MCP server connects and responds to tool calls
- [ ] All 38 CLI commands function identically
- [ ] All 41 MCP tools function identically

### 5.4 Cross-compatibility

- [ ] JWT token from FastAPI works if checked by CLI (same secret)
- [ ] API keys created via old system work in new system
- [ ] API keys created via new system work in CLI/MCP
- [ ] Session created in old system works in new system (cookie compat)

---

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| SQL query differences (Prisma `$queryRawUnsafe` vs asyncpg) | Data discrepancies | Port SQL strings verbatim; diff test every endpoint |
| BigInt/Decimal serialization differences | Frontend parsing errors | Ensure asyncpg returns JSON-compatible types; add serialization middleware |
| JWT cross-compatibility | Session invalidation | Use identical algorithm (HS256), secret, and payload structure |
| Cookie domain/path differences | Auth failures | Mirror exact cookie settings (name, httpOnly, secure, sameSite, maxAge, path) |
| Filter SQL injection | Security vulnerability | Port the exact whitelist from `VALID_FILTER_COLUMNS`; parameterize all values |
| Date range boundary differences (timezone handling) | Off-by-one in queries | Use UTC consistently; test with `date-fns` (JS) vs `datetime` (Python) |
| Missing `next/font` optimization | Larger font downloads, FOUT | Use `font-display: swap` and preload critical fonts |
| Loss of Next.js SSR/streaming | Slower initial page load | Vite SPA is acceptable for a dashboard app; add loading skeletons |

---

## Migration Order Summary

```
Phase 0: Setup directories, init Vite + FastAPI projects
   ↓
Phase 1: Build FastAPI backend (database → auth → queries → routes)
   ↓  Test: API parity with curl/diff against Next.js
   ↓
Phase 2: Build Vite frontend (copy components → routing → pages)
   ↓  Test: Full UI against new FastAPI backend
   ↓
Phase 3: Remove Next.js (delete src/app/, next.config.ts, etc.)
   ↓  Test: CLI/MCP still work, no broken imports
   ↓
Phase 4: Docker & deployment (multi-container setup)
   ↓  Test: Full stack in Docker
   ↓
Phase 5: Verification (full checklist)
```

**Estimated file count:**
- Backend: ~30 Python files
- Frontend: ~60 TypeScript/TSX files (mostly copied with minor edits)
- Config: ~10 files (Dockerfiles, configs, package.json updates)
- Deleted: ~30 Next.js-specific files (src/app/)
