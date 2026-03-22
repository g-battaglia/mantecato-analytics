# MCP Server

Mantecato exposes all analytics data via the [Model Context Protocol](https://modelcontextprotocol.io/), enabling AI agents (Claude, OpenCode, Cursor, etc.) to query analytics data programmatically.

## Setup

### Prerequisites

1. A running Mantecato instance with access to the database
2. An API key generated from the web UI (Settings > API Keys)

### OpenCode

Add to `~/.config/opencode/config.json`:

```json
{
  "mcpServers": {
    "mantecato": {
      "command": "npx",
      "args": ["tsx", "/path/to/mantecato/src/mcp/server.ts"],
      "env": {
        "DATABASE_URL": "postgresql://...",
        "MANTECATO_API_KEY": "mtk_your-key-here"
      }
    }
  }
}
```

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mantecato": {
      "command": "npx",
      "args": ["tsx", "/path/to/mantecato/src/mcp/server.ts"],
      "env": {
        "DATABASE_URL": "postgresql://...",
        "MANTECATO_API_KEY": "mtk_your-key-here"
      }
    }
  }
}
```

### Docker

```json
{
  "mcpServers": {
    "mantecato": {
      "command": "docker",
      "args": [
        "compose", "-f", "/path/to/mantecato/docker-compose.yaml",
        "--profile", "mcp", "run", "--rm", "-i", "mcp"
      ],
      "env": {
        "DATABASE_URL": "postgresql://...",
        "MANTECATO_API_KEY": "mtk_your-key-here"
      }
    }
  }
}
```

### Running Directly

```bash
export DATABASE_URL="postgresql://..."
export MANTECATO_API_KEY="mtk_your-key-here"
npm run mcp
```

## Available Tools (41)

### Core Analytics

| Tool | Description |
|------|-------------|
| `list_sites` | List all tracked websites |
| `get_stats` | Overview stats for a site |
| `get_timeseries` | Pageview & visitor time series |
| `get_comparison` | Compare current vs previous period |

### Pages

| Tool | Description |
|------|-------------|
| `get_pages` | Page analytics with views, time-on-page, bounce rate |
| `get_page_detail` | Referrers, next pages, time distribution, time series for a page |
| `get_top_pages` | Quick top pages by visitors |

### Sources

| Tool | Description |
|------|-------------|
| `get_sources` | Traffic sources with bounce rate and duration |
| `get_referrer_pages` | Pages a specific referrer drives traffic to |
| `get_channels` | Auto-grouped traffic channels |
| `get_utm` | UTM parameter breakdown |
| `get_click_ids` | Click ID analysis |
| `get_hostnames` | Hostname breakdown |
| `get_top_referrers` | Quick top referrers |

### Events

| Tool | Description |
|------|-------------|
| `get_events` | Custom event metrics |
| `get_event_detail` | Time series and properties for a specific event |
| `get_top_events` | Quick top events |

### Sessions

| Tool | Description |
|------|-------------|
| `get_sessions` | Session list with location, device, engagement data |
| `get_session_activity` | Full event replay for a session |

### Devices & Geo

| Tool | Description |
|------|-------------|
| `get_devices` | Device/browser/OS/screen/language breakdown |
| `get_geo` | Country/region/city breakdown with drill-down |
| `get_realtime` | Real-time active visitors |

### Advanced

| Tool | Description |
|------|-------------|
| `get_retention` | Cohort retention analysis |
| `run_funnel` | Funnel analysis with conversion rates |
| `get_journeys` | User journey paths |
| `get_revenue` | Revenue analytics |
| `get_engagement` | Engagement metrics (percentiles, distribution) |
| `get_filter_values` | Available filter values (for autocomplete) |

### CRUD

| Tool | Description |
|------|-------------|
| `list_annotations` | List annotations for a site |
| `create_annotation` | Create annotation on timeline |
| `delete_annotation` | Delete annotation |
| `list_saved_views` | List saved views |
| `get_saved_view` | Get saved view details |
| `create_saved_view` | Create saved view (filters + date preset) |
| `delete_saved_view` | Delete saved view |
| `list_dashboards` | List custom dashboards |
| `get_dashboard` | Get dashboard details |
| `delete_dashboard` | Delete dashboard |
| `list_scheduled_exports` | List scheduled exports |
| `get_scheduled_export` | Get export details |
| `delete_scheduled_export` | Delete scheduled export |

## Common Parameters

All analytics tools accept:

| Parameter | Type | Description |
|-----------|------|-------------|
| `site` | string | Site name, domain, or UUID (required) |
| `period` | string | Date preset: `7d`, `30d`, `90d` (default: `30d`) |
| `start` | string | Custom start date (ISO 8601) |
| `end` | string | Custom end date (ISO 8601) |
| `limit` | number | Max results (default: 20) |
| `filters` | string[] | Array of `column:operator:value` strings |

## Tool Call Examples

### Get overview stats

```json
{
  "name": "get_stats",
  "arguments": {
    "site": "kerykeion.net",
    "period": "30d"
  }
}
```

### Get pages filtered by country

```json
{
  "name": "get_pages",
  "arguments": {
    "site": "kerykeion.net",
    "period": "30d",
    "filters": ["country:eq:US"],
    "limit": 10
  }
}
```

### Run a funnel analysis

```json
{
  "name": "run_funnel",
  "arguments": {
    "site": "kerykeion.net",
    "steps": [
      { "type": "url", "value": "/" },
      { "type": "url", "value": "/content/docs" },
      { "type": "event", "value": "signup-complete" }
    ],
    "period": "30d"
  }
}
```

### Create an annotation

```json
{
  "name": "create_annotation",
  "arguments": {
    "site": "kerykeion.net",
    "title": "Deployed v2.0",
    "date": "2026-03-21",
    "color": "green"
  }
}
```

## Authentication

The MCP server authenticates via the `MANTECATO_API_KEY` environment variable. See [Authentication](./authentication.md) for details on generating and managing API keys.
