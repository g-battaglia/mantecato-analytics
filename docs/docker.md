# Container Deployment

Run Mantecato in containers using Docker Compose, Docker, Apple Containers, or Podman. The production stack is split into a Vite frontend container and a FastAPI backend container, with optional CLI and MCP containers.

## Compatibility

- **Docker Desktop** (macOS, Windows, Linux)
- **Apple Containers** (macOS Sequoia+) — no Docker daemon needed
- **Podman** — drop-in Docker replacement
- **ARM64 & AMD64** — both architectures supported natively

---

## Quick Start with Docker Compose

### 1. Set up your `.env` file

```env
DATABASE_URL=postgresql://user:pass@host:5432/dbname?sslmode=require
SESSION_SECRET=your-random-secret-here
MANTECATO_API_KEY=mtk_your-key-here
```

### 2. Start the dashboard

```bash
docker compose up -d --build
```

The frontend is available at `http://localhost:4180`.
The backend API is available at `http://localhost:8100`.

### 3. Use the CLI via Docker

```bash
docker compose --profile cli run --rm cli stats --site kerykeion.net
docker compose --profile cli run --rm cli pages --site kerykeion.net --format json
```

### 4. Use the MCP server via Docker

```bash
docker compose --profile mcp run --rm -i mcp
```

---

## Standalone Image Builds

### Frontend

```bash
docker build -t mantecato-frontend:latest ./frontend
docker run -d --name mantecato-frontend -p 4180:80 mantecato-frontend:latest
```

### Backend

```bash
docker build -t mantecato-backend:latest ./backend
docker run -d --name mantecato-backend -p 8100:8100 --env-file .env mantecato-backend:latest
```

### CLI / MCP

```bash
docker build -t mantecato-cli:latest -f Dockerfile.cli .

docker run --rm --env-file .env mantecato-cli:latest \
  npx tsx src/cli/index.ts stats --site kerykeion.net --period 30d

docker run --rm -i --env-file .env mantecato-cli:latest \
  npx tsx src/mcp/server.ts
```

---

## Configuration

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string (your Umami database) |
| `SESSION_SECRET` | Yes | Secret for JWT session tokens (any random string) |
| `MANTECATO_API_KEY` | For CLI/MCP | API key for authentication |
| `FRONTEND_PORT` | No | Host port for the frontend container (default: 4180) |
| `BACKEND_PORT` | No | Host port for the backend container (default: 8100) |

### Custom port

```bash
# Docker Compose
FRONTEND_PORT=8080 BACKEND_PORT=8101 docker compose up -d
```

### Database

Mantecato connects to your existing Umami PostgreSQL database (e.g., Neon, Supabase, RDS). It does not include its own database container.

---

## Images Included

| Image | Purpose |
|-------|---------|
| `frontend/Dockerfile` | Builds the Vite app and serves it with nginx |
| `backend/Dockerfile` | Runs FastAPI on port `8100` |
| `Dockerfile.cli` | Runs the shared TypeScript CLI and MCP code with Prisma |

---

## Production Tips

1. **HTTPS** — Put a reverse proxy in front of the frontend container for TLS termination.
2. **Backend secrets** — Keep `DATABASE_URL` and `SESSION_SECRET` only on the backend and CLI/MCP containers.
3. **Auto-restart** — Both frontend and backend containers are configured with `unless-stopped` in Compose.
4. **Database** — Mantecato is read-only except for the `report` table (API keys, saved views, dashboards, and exports).

## Multi-Architecture Builds

```bash
# Docker buildx (frontend)
docker buildx build --platform linux/amd64,linux/arm64 -t mantecato-frontend ./frontend

# Docker buildx (backend)
docker buildx build --platform linux/amd64,linux/arm64 -t mantecato-backend ./backend
```

## Apple Containers Tips

- **Memory**: Give frontend builds at least 2GB.
- **CPU**: Use `--cpus 4` for faster frontend bundle builds.
- **No Docker daemon**: Apple Containers runs lightweight Linux VMs via Virtualization.framework.
- **OCI compatible**: The Dockerfiles work with `container`, `docker`, and `podman`.
