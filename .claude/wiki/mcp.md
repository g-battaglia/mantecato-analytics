# MCP Server

`mcp/mantecato_mcp/` — 41-tool MCP server for AI agent integration. Supports stdio and HTTP transports.

## Running

```bash
# Stdio (default — for Claude Desktop, Claude Code, Cursor, etc.)
cd mcp && PYTHONPATH=../core DATABASE_URL=... uv run mantecato-mcp

# HTTP (for remote deployment, Claude.ai integrations)
cd mcp && PYTHONPATH=../core DATABASE_URL=... MCP_API_KEY=... uv run mantecato-mcp --transport http --port 8200
```

## Transport Modes

### Stdio (default)
Standard MCP stdio transport. Used for local tools in Claude Desktop, Claude Code, OpenCode, Cursor, Cline.

### HTTP (StreamableHTTP)
Remote HTTP transport via `StreamableHTTPSessionManager`. Endpoints:

| Path | Method | Purpose |
|------|--------|---------|
| `/health` | GET | Healthcheck |
| `/mcp` | GET/POST/DELETE | MCP protocol endpoint |
| `/.well-known/oauth-protected-resource` | GET | OAuth discovery |
| `/.well-known/oauth-authorization-server` | GET | OAuth metadata |
| `/oauth/register` | POST | Dynamic client registration |
| `/oauth/authorize` | GET | Authorization endpoint |
| `/oauth/token` | POST | Token exchange (client_credentials + authorization_code) |

**Auth:** Bearer token via `MCP_API_KEY` env var. Returns 401 with `WWW-Authenticate` header for OAuth discovery.

## Operating Modes

1. **Direct DB** (default) — Requires `DATABASE_URL`. Imports from `mantecato_core.queries.*` directly.
2. **Remote API** — Set `MANTECATO_API_URL`. Proxies tool calls to the FastAPI backend via `RemoteClient`.

## 41 Tools

**Core:** list_sites, get_stats, get_timeseries, get_comparison
**Pages:** get_pages, get_page_detail, get_top_pages
**Sources:** get_referrers, get_pages_for_referrer, get_utm, get_channels, get_clickids, get_hostnames, get_top_referrers
**Events:** get_events, get_event_detail, get_top_events
**Sessions:** get_sessions, get_session_activity
**Devices:** get_devices
**Geo:** get_geo
**Advanced:** get_active_visitors, get_retention, get_funnel, get_journeys, get_revenue, get_engagement, get_filter_values
**CRUD:** Annotations, saved views, dashboards, scheduled exports (list/get/create/delete)

## Tool Input Schema

All tools accept standard properties:
- `site` (required): Site name, domain, or UUID
- `period`: Date preset (default: 30d)
- `start` / `end`: ISO 8601 custom range
- `filter`: Array of `column:operator:value` strings
- `granularity`: auto|minute|hour|day|week|month
- `limit`: Max rows (default: 20)

## Key Files

| File | Purpose |
|------|---------|
| `server.py` | Server, 41 tools, HTTP transport, OAuth endpoints (~1,600 lines) |
| `remote.py` | RemoteClient for API proxy mode |

## Client Configuration

**Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "mantecato": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mantecato/mcp", "mantecato-mcp"],
      "env": { "DATABASE_URL": "postgresql://...", "PYTHONPATH": "/path/to/mantecato/core" }
    }
  }
}
```

**Remote (Claude.ai / Claude Desktop)**:
```json
{
  "mcpServers": {
    "mantecato": {
      "url": "https://<service>.up.railway.app/mcp",
      "headers": { "Authorization": "Bearer <MCP_API_KEY>" }
    }
  }
}
```
