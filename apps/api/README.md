# apps/api -- JSON API for CLI and MCP

Headless JSON API for programmatic access to Mantecato. It produces no HTML:
all responses are `application/json`. Used by the CLI (`mantecato`),
the MCP server, and the Python SDK (`mantecato-client`).

## Purpose

The JSON API exposes the same functionality as the web dashboard, but with
pure JSON serialization. The views call the same service functions
(`apps/analytics/services.py`, `apps/dashboards/services.py`,
`apps/settings_app/services.py`) used by the HTML views, ensuring
identical behavior.

## Authentication

All requests require the header:

```
Authorization: Bearer mtk_...
```

API keys are generated from the web dashboard (Settings > API Keys) or
from the CLI (`mantecato api-key-create`). Keys are hashed with SHA-256 before
storage: the plaintext value is shown only at creation time.

**Key scopes:**

- Keys with `admin` scope can access all sites
- Regular keys can only see sites that the owning user has access to

Authentication is handled by the `ApiKeyMiddleware`
(`mantecato/middleware.py`), which validates the token and injects `request.api_user_id`
and `request.api_key_scopes` into the request.

## Available Endpoints

All paths are prefixed with `/api/`.

### Sites

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/sites/` | List of sites accessible to the user |

### Analytics (read-only)

All accept the query params `website` (UUID, required), `start_at`, `end_at`,
and filters.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/analytics/overview/` | Aggregate metrics, charts, events, devices, geo, heatmap |
| `GET` | `/api/analytics/pages/` | Per-page pageview metrics (paginated, `page` param) |
| `GET` | `/api/analytics/events/` | Custom event-name counts and timelines |
| `GET` | `/api/analytics/devices/` | Breakdown by browser, OS, device |
| `GET` | `/api/analytics/geo/` | Country-level pageview distribution |
| `GET` | `/api/analytics/compare/` | Current vs previous period comparison (`mode` param) |
| `GET` | `/api/analytics/realtime/` | Live pageview counters (`website` param only) |

### Dashboards (CRUD)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/dashboards/` | List dashboards (optional `website` param) |
| `GET` | `/api/dashboards/<uuid>/` | Single dashboard detail |
| `POST` | `/api/dashboards/create/` | Create dashboard (body: `name`, `website_id`, `description`, `config`) |
| `POST` | `/api/dashboards/<uuid>/update/` | Update dashboard (body: `name`, `description`, `config`) |
| `POST` | `/api/dashboards/<uuid>/delete/` | Delete dashboard |

### API Keys (CRUD)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/api-keys/` | List the user's API keys |
| `POST` | `/api/api-keys/create/` | Generate a new API key (body: `name`, `scopes`) |
| `POST` | `/api/api-keys/<uuid>/delete/` | Revoke an API key |

### Bot Config

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/bot-config/?website=<uuid>` | Bot detection configuration |
| `POST` | `/api/bot-config/save/` | Save bot configuration (body: `website_id`, `config`) |

## Request Format

### Read (GET)

Parameters are passed as query string:

```
GET /api/analytics/pages/?website=<uuid>&start_at=1704067200&end_at=1706745600&page=1
```

### Write (POST)

The body is JSON with `Content-Type: application/json`:

```bash
curl -X POST https://analytics.example.com/api/dashboards/create/ \
  -H "Authorization: Bearer ${MANTECATO_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"name": "Sales Dashboard", "website_id": "<uuid>", "description": "E-commerce KPIs"}'
```

## Response Format

All responses are JSON. Successful responses return data directly
(without an envelope wrapper):

```json
{
  "websites": [
    {"id": "uuid-1", "name": "Main Site", "domain": "example.com"}
  ]
}
```

Delete operations return:

```json
{"deleted": true}
```

## Error Codes

| Status | Meaning | Example body |
|---|---|---|
| 400 | Missing or invalid parameters | `{"error": "No accessible website found."}` |
| 401 | Missing or invalid API key | `{"error": "Authentication required."}` |
| 403 | Access denied to the requested site | `{"error": "Website not accessible."}` |
| 404 | Resource not found | `{"error": "Dashboard not found."}` |

## Architecture

```
apps/api/urls.py        Routing: path -> view
apps/api/views.py       Class-based views (no DRF)
    |
    |-- ApiAuthMixin            Authentication via Bearer token
    |-- WebsiteContextMixin     Resolves website_id from the request
    |-- DateRangeMixin          Date range parsing
    |-- FiltersMixin            Filter parsing
    |
    v
apps/analytics/services.py     Analytics logic (shared with the web dashboard)
apps/dashboards/services.py    Dashboard logic
apps/settings_app/services.py  API key, bot config, scheduled export logic
```

The views are standard Django `View` classes (no Django REST Framework), with mixins
that handle authentication, parameter parsing, and access control.
The two main patterns are:

- `_AnalyticsJSONView`: for analytics GET endpoints, with dynamic service
  function resolution via `service_name`
- Individual CRUD views: for create, update, and delete operations
