# Core Module

`core/mantecato_core/` — Framework-agnostic shared library. Only dependency: `asyncpg`.

## Key Files

| File | Purpose |
|------|---------|
| `database.py` | asyncpg pool creation, `raw_query()` with retry logic, parameter substitution |
| `filters.py` | Filter dataclass, SQL WHERE builder, bot filter SQL |
| `date_utils.py` | DateRange class, 20+ presets, granularity resolution |
| `helpers.py` | `list_sites()`, `resolve_site_id()`, `parse_date_args()`, `compute_derived_stats()` |
| `config.py` | XDG config directory (`~/.config/mantecato/config.toml`) |

## Query Modules (23 files in `queries/`)

**Analytics:** stats, pageviews, timeseries, compare, realtime
**Sources:** sources (referrers, UTM, channels, clickids, hostnames)
**Behavior:** sessions, events, journeys, retention, engagement
**Conversion:** funnels, revenue
**Geo/Devices:** geo (country/region/city), devices (browser/OS/screen/language)
**Admin:** api_keys, saved_views, dashboards, scheduled_exports, annotations, bot_config
**Utility:** filter_values, heatmap

## Parameter Substitution

```sql
SELECT * FROM website_event
WHERE website_id = {{websiteId::uuid}}
  AND created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
```

Regex replaces `{{param::type}}` with positional `$1`, `$2` and builds an args list. Supports type casts (`::uuid`, `::timestamptz`).

## Filter System

**Format:** `column:operator:value`
**Columns (16):** url_path, page_title, hostname, referrer_domain, utm_source, utm_medium, utm_campaign, event_name, tag, browser, os, device, country, region, city, language, screen
**Operators:** eq, neq, contains, not_contains, starts_with, not_starts_with

Generates parameterized WHERE clauses with session table joins when filtering on session-level columns.

## Date Presets

1h, 3h, 6h, today, yesterday, 24h, 7d, 14d, 30d, 60d, 90d, 6m, 12m, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, all

**Auto-granularity:** ≤6h→minute, ≤1d→hour, ≤90d→day, ≤365d→week, >365d→month

## Bot Detection

1. **Known bots** — Browser SIMILAR TO regex (bot/crawler/spider/headless keywords)
2. **Empty UA** — Both browser and os fields empty
3. **Cluster detection** — Country+device groups with >100 sessions and >90% bounce rate

Configurable per-site via `bot_config` table.
