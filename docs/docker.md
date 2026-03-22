# Container Deployment

Mantecato provides a multi-stage Dockerfile optimized for production deployment. It builds on `node:22-alpine` and produces a minimal image using Next.js standalone output.

## Compatibility

- **Apple Containers** (macOS Sequoia+) — native `container` CLI, no Docker daemon needed
- **Docker Desktop** (macOS, Windows, Linux)
- **Podman** — drop-in Docker replacement
- **ARM64 & AMD64** — the Alpine base image supports both architectures natively

## Quick Start with Apple Containers

### 1. Create a `.env` file

```env
DATABASE_URL=postgresql://user:pass@host:5432/dbname?sslmode=require
SESSION_SECRET=your-random-secret-here
MANTECATO_API_KEY=mtk_your-key-here
```

### 2. Build the image

```bash
container build -t mantecato:latest --memory 4096MB --cpus 4 .
```

> First build takes ~5 minutes (npm install inside the VM). Subsequent builds use layer caching.

### 3. Run the web dashboard

```bash
container run -d --name mantecato-web \
  -p 3000:3000 \
  --env-file .env \
  mantecato:latest
```

The dashboard is available at `http://localhost:3000`.

### 4. Use the CLI via container

```bash
container run --rm \
  --env-file .env \
  --entrypoint "npx" \
  mantecato:latest \
  tsx src/cli/index.ts stats --site kerykeion.net --period 30d
```

### 5. Use the MCP server via container

```bash
container run --rm -i \
  --env-file .env \
  --entrypoint "npx" \
  mantecato:latest \
  tsx src/mcp/server.ts
```

### 6. Container management

```bash
# View logs
container logs mantecato-web

# Stop
container stop mantecato-web

# Remove
container rm mantecato-web

# List running containers
container ls

# Resource usage
container stats
```

## Quick Start with Docker Compose

If you prefer Docker Desktop or have `docker compose` available:

### Start the web dashboard

```bash
docker compose up -d
```

### Use the CLI

```bash
docker compose --profile cli run --rm cli stats --site kerykeion.net
docker compose --profile cli run --rm cli pages --site kerykeion.net --format json
```

### Use the MCP server

```bash
docker compose --profile mcp run --rm -i mcp
```

## Architecture

The Dockerfile uses a 3-stage build:

| Stage | Purpose | Base |
|-------|---------|------|
| `deps` | Install npm dependencies | `node:22-alpine` |
| `builder` | Generate Prisma client, build Next.js | `node:22-alpine` |
| `runner` | Production runtime (minimal) | `node:22-alpine` |

The final image contains only:
- Next.js standalone server (`server.js`)
- Static assets (`.next/static`)
- Public files
- Prisma client and schema
- CLI and MCP source files (for optional use)

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `SESSION_SECRET` | Yes | Secret for JWT session tokens |
| `MANTECATO_API_KEY` | For CLI/MCP | API key for authentication |
| `PORT` | No | Web server port (default: 3000) |

### Custom Port

```bash
# Apple Containers
container run -d -p 8080:3000 --env-file .env mantecato:latest

# Docker Compose
PORT=8080 docker compose up -d
```

### External Database

The container setup assumes you have an external PostgreSQL database (e.g., Neon, Supabase, RDS). Mantecato reads from the Umami database — it does not include its own database container.

## Apple Containers Tips

- **Memory**: The builder stage needs at least 2GB. Use `--memory 4096MB` for faster builds.
- **CPU**: Allocate more CPUs with `--cpus 4` for faster `npm ci` and `next build`.
- **No Docker daemon**: Apple Containers runs lightweight Linux VMs natively via Virtualization.framework — no Docker Desktop license needed.
- **OCI compatible**: The same Dockerfile and images work with `container`, `docker`, and `podman`.
- **Networking**: Published ports (`-p`) work the same as Docker.
- **Volumes**: Use `--volume` or `--mount` for persistent data if needed.

## Building for Multiple Architectures

```bash
# Apple Containers (ARM64 only, native)
container build -t mantecato:latest .

# Docker buildx (multi-arch)
docker buildx build --platform linux/amd64,linux/arm64 -t mantecato .
```

## Production Considerations

1. **TLS**: Use a reverse proxy (nginx, Caddy, Traefik) for HTTPS termination
2. **Health checks**: The compose file includes a health check on `http://localhost:3000`
3. **Restart policy**: Set to `unless-stopped` for automatic recovery (Docker Compose)
4. **Non-root**: The production image runs as user `nextjs` (UID 1001)
5. **Read-only database**: Mantecato only writes to the `report` table
