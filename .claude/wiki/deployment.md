# Deployment

All deploy scripts and configs live in `deploy/` (gitignored — never committed).

## Infrastructure

| Service | Platform | URL |
|---------|----------|-----|
| Backend API | Railway | `https://backend-production-636f4.up.railway.app` |
| MCP Server | Railway | `https://mcp-server-production-0de1.up.railway.app` |
| Frontend | Cloudflare Pages | `https://mantecato.pages.dev` |
| Database | Railway (Postgres) | Internal: `postgres.railway.internal` |

## Railway Deploy Pattern (Backend + MCP)

Railway uses Nixpacks for builds. The monorepo requires a file-swap trick:

1. Hide `package.json` + `package-lock.json` (prevents Node.js detection)
2. Copy service-specific `requirements.txt` + `railway.json` to root
3. Run `railway up --detach`
4. Restore files via `trap cleanup EXIT`

**Key insight:** `PYTHONPATH=/app/core` makes `mantecato_core` importable without pip-installing it as a package.

## Deploy Scripts

```bash
# Backend
bash deploy/deploy-backend.sh

# MCP Server
railway service link mcp-server
bash deploy/deploy-mcp.sh

# Frontend
bash deploy/deploy-frontend.sh
```

## Railway Environment Variables

### Backend
| Variable | Value |
|----------|-------|
| `DATABASE_URL` | Reference from Postgres service |
| `SESSION_SECRET` | JWT signing key |
| `CORS_ORIGINS` | `["https://mantecato.pages.dev","http://localhost:4180"]` |
| `PYTHONPATH` | `/app/core` |

### MCP Server
| Variable | Value |
|----------|-------|
| `DATABASE_URL` | Same Postgres reference |
| `MCP_API_KEY` | Bearer token for auth |
| `PYTHONPATH` | `/app/core` |

## Frontend (Cloudflare Pages)

Built with `VITE_API_URL` pointing to the Railway backend:

```bash
cd frontend
VITE_API_URL="https://backend-production-636f4.up.railway.app" npm run build
npx wrangler pages deploy dist --project-name mantecato --commit-dirty=true
```

## Deploy Files (all in `deploy/`, gitignored)

| File | Purpose |
|------|---------|
| `deploy-backend.sh` | Backend Railway deploy script |
| `deploy-mcp.sh` | MCP server Railway deploy script |
| `deploy-frontend.sh` | Frontend Cloudflare Pages deploy |
| `railway.json` | Backend Railway config |
| `mcp-railway.json` | MCP Railway config |
| `requirements.txt` | Backend flat Python deps |
| `mcp-requirements.txt` | MCP flat Python deps |
| `README.md` | Deploy documentation + secrets reference |

## Docker (Local)

```bash
docker compose up -d --build
# Frontend: localhost:4180, API: localhost:8100
```

Profiles: `--profile cli` for CLI, `--profile mcp` for MCP server.
