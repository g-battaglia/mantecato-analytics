# Backend

`backend/app/` — FastAPI REST API server. Depends on `mantecato-core`.

## Entry Point

```bash
cd backend && uv run python -m uvicorn app.main:app --port 8100 --reload
```

`app/main.py` — FastAPI app with CORS middleware, lifespan pool management, 24 routers.

## Authentication

**File:** `app/auth.py`

- JWT HS256 tokens via python-jose, 7-day expiration
- bcrypt password hashing (compatible with bcryptjs)
- Access control: admin sees all sites, regular users see own + team sites

## API Key System

- Prefix: `mtk_` + random token
- Stored as SHA-256 hash, full key shown once at creation
- Scopes: `["read"]`, `["write"]`, or both

## Configuration

**File:** `app/config.py` — Pydantic settings

- `CORS_ORIGINS: list[str]` — Requires JSON array format in env vars OR comma-separated (field_validator handles both)
- Reads from `../.env` by default

## Routes (27 modules in `app/routers/`)

| Module | Endpoints |
|--------|-----------|
| auth | POST /login, /logout, /register |
| sites | GET /sites |
| stats | GET /stats |
| pages | GET /pages, /pages/:url |
| sources | GET /sources, /referrers, /utm, /channels, /clickids, /hostnames |
| events | GET /events, /events/:name |
| sessions | GET /sessions, /sessions/:id/activity |
| devices | GET /devices |
| geo | GET /geo |
| realtime | GET /realtime/visitors, /realtime/events |
| compare | GET /compare |
| retention | GET /retention |
| funnels | POST /funnels |
| journeys | GET /journeys |
| revenue | GET /revenue |
| engagement | GET /engagement |
| filter_values | GET /filter-values/:column |
| annotations | GET/POST/DELETE /annotations |
| saved_views | GET/POST/DELETE /saved-views |
| dashboards | GET/POST/DELETE /dashboards, /dashboards/:id/widgets |
| scheduled_exports | GET/POST/DELETE /scheduled-exports |
| api_keys | GET/POST/DELETE /api-keys |
| script | GET /api/script (tracker delivery) |
| share | GET /share/:shareId (public dashboards) |
| cron | POST /cron/:task |
| bot_config | GET/POST /bot-config |

All analytics routes import queries from `mantecato_core.queries.*`.
