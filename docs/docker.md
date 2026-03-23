# Container Deployment

Run Mantecato in a container using Docker, Apple Containers, or Podman. The included Dockerfile produces a minimal production image based on `node:22-alpine`.

## Compatibility

- **Docker Desktop** (macOS, Windows, Linux)
- **Apple Containers** (macOS Sequoia+) — no Docker daemon needed
- **Podman** — drop-in Docker replacement
- **ARM64 & AMD64** — both architectures supported natively

---

## Quick Start with Docker Compose

The simplest way to run Mantecato in a container.

### 1. Set up your `.env` file

```env
DATABASE_URL=postgresql://user:pass@host:5432/dbname?sslmode=require
SESSION_SECRET=your-random-secret-here
MANTECATO_API_KEY=mtk_your-key-here
```

### 2. Start the dashboard

```bash
docker compose up -d
```

The dashboard is available at `http://localhost:3000`.

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

## Quick Start with Apple Containers

If you're on macOS Sequoia+ and prefer Apple's native container runtime:

### Build

```bash
container build -t mantecato:latest --memory 4096MB --cpus 4 .
```

> First build takes ~5 minutes. Subsequent builds use layer caching.

### Run the dashboard

```bash
container run -d --name mantecato-web \
  -p 3000:3000 \
  --env-file .env \
  mantecato:latest
```

### Run CLI commands

```bash
container run --rm \
  --env-file .env \
  --entrypoint "npx" \
  mantecato:latest \
  tsx src/cli/index.ts stats --site kerykeion.net --period 30d
```

### Run the MCP server

```bash
container run --rm -i \
  --env-file .env \
  --entrypoint "npx" \
  mantecato:latest \
  tsx src/mcp/server.ts
```

### Manage containers

```bash
container logs mantecato-web    # View logs
container stop mantecato-web    # Stop
container rm mantecato-web      # Remove
container ls                    # List running
container stats                 # Resource usage
```

---

## Configuration

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string (your Umami database) |
| `SESSION_SECRET` | Yes | Secret for JWT session tokens (any random string) |
| `MANTECATO_API_KEY` | For CLI/MCP | API key for authentication |
| `PORT` | No | Web server port (default: 3000) |

### Custom port

```bash
# Apple Containers
container run -d -p 8080:3000 --env-file .env mantecato:latest

# Docker Compose
PORT=8080 docker compose up -d
```

### Database

Mantecato connects to your existing Umami PostgreSQL database (e.g., Neon, Supabase, RDS). It does not include its own database container.

---

## How the Image Is Built

The Dockerfile uses a 3-stage build for minimal image size:

| Stage | What it does |
|-------|-------------|
| `deps` | Installs npm dependencies |
| `builder` | Generates Prisma client, builds Next.js |
| `runner` | Production runtime with only the essentials |

The final image contains the Next.js standalone server, static assets, Prisma client, and CLI/MCP source files.

---

## Production Tips

1. **HTTPS** — Use a reverse proxy (nginx, Caddy, Traefik) for TLS termination
2. **Health checks** — The Docker Compose file includes a health check on port 3000
3. **Auto-restart** — Set to `unless-stopped` for automatic recovery
4. **Security** — The image runs as a non-root user (`nextjs`, UID 1001)
5. **Database** — Mantecato is read-only except for the `report` table (API keys, saved views, etc.)

## Multi-Architecture Builds

```bash
# Apple Containers (ARM64 only)
container build -t mantecato:latest .

# Docker buildx (multi-arch)
docker buildx build --platform linux/amd64,linux/arm64 -t mantecato .
```

## Apple Containers Tips

- **Memory**: Use `--memory 4096MB` — the build needs at least 2GB.
- **CPU**: Use `--cpus 4` for faster builds.
- **No Docker daemon**: Runs lightweight Linux VMs via Virtualization.framework.
- **OCI compatible**: The same Dockerfile works with `container`, `docker`, and `podman`.
