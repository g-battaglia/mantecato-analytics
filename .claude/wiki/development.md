# Development

## Prerequisites

- Python 3.12+, uv
- Node.js 20+, npm
- PostgreSQL (or `DATABASE_URL` to an existing Umami DB)

## Running Services

```bash
# Backend API (port 8100)
cd backend && uv run python -m uvicorn app.main:app --port 8100 --reload

# Frontend (port 4180)
cd frontend && npm run dev

# CLI
cd cli && uv run mantecato <command> -s <site> -p 30d

# MCP Server (stdio)
cd mcp && PYTHONPATH=../core uv run mantecato-mcp

# MCP Server (HTTP, port 8200)
cd mcp && PYTHONPATH=../core MCP_API_KEY=test uv run mantecato-mcp --transport http
```

## Package Installation

Each Python package requires `mantecato-core` as a local dependency:

```bash
# In a venv for testing
uv venv .venv
uv pip install --python .venv/bin/python /path/to/core /path/to/mcp
```

For uv projects, `PYTHONPATH=../core` is the simplest workaround since `mantecato-core` isn't published to PyPI.

## Configuration

CLI config: `~/.config/mantecato/config.toml`

```toml
[database]
url = "postgresql://..."

[defaults]
site = "mysite.com"
```

Environment: `.env` file at project root (gitignored).

## Important Conventions

- **No ORM** — Raw SQL with `{{param::type}}` substitution
- **No Next.js** — Pure Vite + React. Do not use next/* APIs
- **Read-only Umami DB** — Never run migrations or write to Umami tables
- **Python 3.12+** — Uses modern typing features
- **asyncpg only** — No SQLAlchemy, no psycopg
