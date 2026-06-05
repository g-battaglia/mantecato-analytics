# mantecato-client

<!-- badges placeholder -->
<!-- [![PyPI](https://img.shields.io/pypi/v/mantecato-client)](https://pypi.org/project/mantecato-client/) -->
<!-- [![Python](https://img.shields.io/pypi/pyversions/mantecato-client)](https://pypi.org/project/mantecato-client/) -->
<!-- [![License](https://img.shields.io/pypi/l/mantecato-client)](LICENSE) -->

Python SDK for the Mantecato API. Lets you query analytics data, manage
dashboards, API keys, and bot configurations from
any Python script or application.

## Installation

```bash
pip install mantecato-client
```

Requires Python 3.10+. The only runtime dependency is `httpx`.

## Quick start

```python
from mantecato_client import MantecatoClient

# Use the context manager to automatically close the HTTP connection
with MantecatoClient("https://analytics.example.com", api_key="mtk_xxx") as client:

    # List tracked sites
    sites = client.sites.list()
    website_id = sites["websites"][0]["id"]

    # Overview of the last 30 days
    overview = client.analytics.overview(website_id, date_range="30d")
    print(overview["stats"]["visitors"]["value"])

    # Top pages over the last 7 days
    pages = client.analytics.pages(website_id, date_range="7d")
    for p in pages["pages"]:
        print(p["url_path"], p["visitors"])
```

## Authentication

All requests require an API key in the `mtk_...` format, which can be generated
from the web dashboard or the CLI. The key is sent as an
`Authorization: Bearer mtk_...` header on every request.

```python
import os

client = MantecatoClient(
    base_url="https://analytics.example.com",
    api_key=os.environ["MANTECATO_API_KEY"],
    timeout=30.0,  # HTTP timeout in seconds (default: 30)
)
```

You can inject a pre-configured `httpx.Client` for advanced scenarios
(proxy, mTLS, testing):

```python
import httpx

http = httpx.Client(verify="/path/to/ca-bundle.crt")
client = MantecatoClient("https://...", api_key="mtk_...", httpx_client=http)
```

## Available Modules

The client exposes seven namespaces, each accessible as an attribute:

| Attribute | Class | Description |
|---|---|---|
| `client.sites` | `SitesEndpoints` | List of tracked sites |
| `client.analytics` | `AnalyticsEndpoints` | Read-only analytics queries |
| `client.dashboards` | `DashboardsEndpoints` | Custom dashboard CRUD |
| `client.api_keys` | `ApiKeysEndpoints` | API key management |
| `client.bot_config` | `BotConfigEndpoints` | Bot detection configuration |

### Analytics Endpoints

The `analytics` module provides 14 read methods:

| Method | Description |
|---|---|
| `overview()` | Aggregate site metrics (visitors, pageviews, bounce rate, ...) |
| `pages()` | Per-URL metrics with pagination |
| `sources()` | Traffic sources: referrers, UTM, channels, click IDs |
| `events()` | Custom event analysis |
| `sessions()` | Session list with pagination |
| `devices()` | Breakdown by browser, OS, device, screen, language |
| `geo()` | Geographic distribution with drill-down (country -> region -> city) |
| `compare()` | Current vs previous period comparison |
| `retention()` | Cohort retention analysis |
| `funnels()` | Multi-step conversion funnel analysis |
| `journeys()` | User journeys with data for Sankey diagrams |
| `revenue()` | Revenue analysis: totals, time series, by event/country |
| `engagement()` | Engagement metrics: duration distribution, percentiles, bounce |
| `realtime()` | Active visitors in real time |

All methods (except `realtime`) accept common parameters:

```python
# Range with shorthand
data = client.analytics.pages(website_id, date_range="30d")

# Range with explicit dates
data = client.analytics.pages(website_id, start="2024-01-01", end="2024-01-31")

# With filters and bot exclusion
data = client.analytics.pages(
    website_id,
    date_range="7d",
    filters=["country:US", "browser:Chrome"],
    bot_filter=True,
)
```

### Example: conversion funnel

```python
result = client.analytics.funnels(
    website_id,
    date_range="30d",
    steps=[("url", "/"), ("url", "/pricing"), ("url", "/signup")],
    window=60,  # conversion window in minutes
)
for step in result["funnel_steps"]:
    print(step["label"], step["visitors"], step["drop_off_rate"])
```

### Example: geo drill-down

```python
# Country level
geo = client.analytics.geo(website_id, date_range="30d")

# Drill down into Italian regions
regions = client.analytics.geo(website_id, date_range="30d", country="IT")

# Drill down into cities in Lombardy
cities = client.analytics.geo(website_id, date_range="30d", country="IT", region="25")
```

## Error Handling

The SDK maps HTTP status codes to typed exceptions:

```python
from mantecato_client import (
    MantecatoClient,
    MantecatoError,
    AuthError,
    NotFoundError,
    ValidationError,
)

try:
    data = client.analytics.overview("nonexistent-uuid", date_range="30d")
except AuthError as e:
    # HTTP 401 or 403: missing, invalid, or unauthorized API key
    print(f"Authentication error: {e} (status={e.status_code})")
except NotFoundError as e:
    # HTTP 404: resource not found
    print(f"Not found: {e}")
except ValidationError as e:
    # HTTP 400: invalid parameters
    print(f"Bad request: {e}")
    print(f"Details: {e.response_body}")
except MantecatoError as e:
    # All other HTTP errors (5xx, etc.)
    print(f"API error: {e} (status={e.status_code})")
```

| HTTP Status | Exception |
|---|---|
| 400 | `ValidationError` |
| 401, 403 | `AuthError` |
| 404 | `NotFoundError` |
| 5xx / other | `MantecatoError` |

All exceptions have `status_code` (int) and `response_body` (dict) attributes.

## Development

```bash
# Clone and install in development mode
cd packages/mantecato-client
pip install -e ".[dev]"

# Linting
ruff check src/ tests/

# Tests
pytest
```

Ruff and pytest configuration is in `pyproject.toml` (line-length 100, target Python 3.10).
