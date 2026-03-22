# Docker Deployment

Mantecato provides a multi-stage Dockerfile optimized for production deployment. It builds on `node:22-alpine` and produces a minimal image using Next.js standalone output.

## Compatibility

- **Docker Desktop** (macOS, Windows, Linux)
- **Apple Containers** (macOS Sequoia+) — uses standard OCI images, fully compatible
- **Podman** — drop-in Docker replacement
- **ARM64 & AMD64** — the Alpine base image supports both architectures natively

## Quick Start

### 1. Create a `.env` file

```env
DATABASE_URL=postgresql://user:pass@host:5432/dbname?sslmode=require
SESSION_SECRET=your-random-secret-here
MANTECATO_API_KEY=mtk_your-key-here
```

### 2. Start the web dashboard

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
PORT=8080 docker compose up -d
```

### External Database

The Docker setup assumes you have an external PostgreSQL database (e.g., Neon, Supabase, RDS). Mantecato reads from the Umami database — it does not include its own database container.

## Apple Containers

[Apple Containers](https://developer.apple.com/documentation/virtualization) (available in macOS Sequoia) works with standard OCI container images. No special configuration is needed:

```bash
# Build
container build -t mantecato .

# Run
container run -p 3000:3000 \
  -e DATABASE_URL="postgresql://..." \
  -e SESSION_SECRET="your-secret" \
  mantecato
```

Or use the `docker` CLI compatibility layer:

```bash
docker compose up -d
```

## Building for Multiple Architectures

```bash
# Build for both ARM64 (Apple Silicon) and AMD64
docker buildx build --platform linux/amd64,linux/arm64 -t mantecato .
```

## Production Considerations

1. **TLS**: Use a reverse proxy (nginx, Caddy, Traefik) for HTTPS termination
2. **Health checks**: The compose file includes a health check on `http://localhost:3000`
3. **Restart policy**: Set to `unless-stopped` for automatic recovery
4. **Non-root**: The production image runs as user `nextjs` (UID 1001)
5. **Read-only database**: Mantecato only writes to the `report` table
