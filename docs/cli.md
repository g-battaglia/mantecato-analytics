# CLI Reference

Mantecato CLI provides full analytics access from the terminal. Every metric available in the web UI can be queried via CLI.

## Installation & Setup

```bash
# Clone and install
git clone https://github.com/g-battaglia/mantecato-analytics.git && cd mantecato-analytics
npm install --legacy-peer-deps

# Generate Prisma client
npx prisma generate

# Set environment variables
export DATABASE_URL="postgresql://..."
export MANTECATO_API_KEY="mtk_your-key-here"
```

## Running

```bash
# Via npm script
npm run cli -- <command> [options]

# Via npx
npx tsx src/cli/index.ts <command> [options]

# Via Docker
docker compose --profile cli run --rm cli <command> [options]
```

## Global Options

Every analytics command supports these options:

| Option | Description | Default |
|--------|-------------|---------|
| `--api-key <key>` | API key (or set `MANTECATO_API_KEY` env var) | required |
| `-s, --site <site>` | Site name, domain, or UUID | required |
| `-p, --period <preset>` | Date preset: `7d`, `30d`, `90d`, `this_month`, etc. | `30d` |
| `--start <date>` | Custom start date (ISO 8601) | - |
| `--end <date>` | Custom end date (ISO 8601) | - |
| `-f, --format <format>` | Output: `json`, `table`, `csv` | `table` |
| `--filter <filter...>` | Filters as `column:operator:value` (repeatable) | - |
| `-l, --limit <n>` | Max rows | `20` |
| `-g, --granularity <g>` | `auto`, `minute`, `hour`, `day`, `week`, `month` | `auto` |

## Site Resolution

The `--site` flag is flexible. All of these work:

```bash
--site kerykeion.net           # by name
--site www.kerykeion.net       # by full domain
--site b52bd153-29af-...       # by UUID
--site kery                    # by partial name match
```

## Commands

### Core Analytics

| Command | Description |
|---------|-------------|
| `sites` | List all tracked websites |
| `stats` | Overview stats (pageviews, visitors, visits, bounce rate, avg duration) |
| `timeseries` | Pageview & visitor time series |
| `compare` | Compare current period vs previous period |

### Pages

| Command | Description |
|---------|-------------|
| `pages` | Page analytics (views, time-on-page, bounce rate, entries/exits) |
| `page-detail --url <path>` | Detailed stats: referrers, next pages, time distribution, time series |
| `top-pages` | Quick top pages by visitors |

### Sources

| Command | Description |
|---------|-------------|
| `sources` | Traffic sources with bounce rate and duration |
| `referrer-pages --referrer <domain>` | Pages a specific referrer drives traffic to |
| `channels` | Auto-grouped traffic channels (Organic, Direct, Social, etc.) |
| `utm` | UTM parameter breakdown |
| `clickids` | Click ID analysis (gclid, fbclid, etc.) |
| `hostnames` | Hostname breakdown |
| `top-referrers` | Quick top referrers |

### Events

| Command | Description |
|---------|-------------|
| `events` | Custom event metrics |
| `event-detail --event <name>` | Time series and properties for a specific event |
| `top-events` | Quick top events |

### Sessions

| Command | Description |
|---------|-------------|
| `sessions` | Session list with location, device, engagement data |
| `session-activity --session-id <id>` | Full event replay for a specific session |

### Devices

| Command | Description |
|---------|-------------|
| `devices` | Device type breakdown (default dimension) |
| `devices --dimension browser` | Browser breakdown |
| `devices --dimension os` | OS breakdown |
| `devices --dimension screen` | Screen resolution breakdown |
| `devices --dimension language` | Language breakdown |

### Geographic

| Command | Description |
|---------|-------------|
| `geo` | Country-level breakdown (default) |
| `geo --level region --country US` | Region drill-down within a country |
| `geo --level city --country US` | City drill-down within a country |

### Advanced Analytics

| Command | Description |
|---------|-------------|
| `realtime` | Real-time active visitors |
| `retention` | Cohort retention analysis |
| `funnel --steps "/,/pricing,/signup"` | Funnel analysis (comma-separated URL steps) |
| `journeys` | User journey paths (page sequences) |
| `revenue` | Revenue analytics |
| `engagement` | Engagement metrics (duration percentiles, distribution) |
| `filter-values --column <col>` | Available values for a filter column (autocomplete) |

### CRUD Operations

| Command | Description |
|---------|-------------|
| `annotations` | List annotations for a site |
| `annotation-create --title <t> --date <d>` | Create annotation |
| `annotation-delete --id <uuid>` | Delete annotation |
| `saved-views` | List saved views |
| `saved-view --id <uuid>` | Get saved view details |
| `saved-view-create --name <n> --config <json>` | Create saved view |
| `saved-view-delete --id <uuid>` | Delete saved view |
| `dashboards` | List custom dashboards |
| `dashboard --id <uuid>` | Get dashboard details |
| `dashboard-delete --id <uuid>` | Delete dashboard |
| `scheduled-exports` | List scheduled exports |
| `scheduled-export --id <uuid>` | Get export details |
| `scheduled-export-delete --id <uuid>` | Delete export |

## Filters

Filters use the format `column:operator:value` and can be repeated:

```bash
# Single filter
mantecato stats --site kerykeion.net --filter country:eq:US

# Multiple filters (AND between columns, OR within same column)
mantecato stats --site kerykeion.net --filter country:eq:US --filter browser:eq:chrome
```

### Operators

| Operator | SQL | Description |
|----------|-----|-------------|
| `eq` | `= value` | Equals |
| `neq` | `!= value` | Not equals |
| `contains` | `ILIKE %value%` | Contains |
| `not_contains` | `NOT ILIKE %value%` | Does not contain |
| `starts_with` | `ILIKE value%` | Starts with |
| `not_starts_with` | `NOT ILIKE value%` | Does not start with |

### Filterable Columns

`url_path`, `page_title`, `hostname`, `referrer_domain`, `utm_source`, `utm_medium`, `utm_campaign`, `event_name`, `tag`, `browser`, `os`, `device`, `country`, `region`, `city`, `language`, `screen`

## Output Formats

```bash
# Table (default) — human-readable with alignment
mantecato top-pages --site kerykeion.net --format table

# JSON — for programmatic consumption and piping
mantecato stats --site kerykeion.net --format json

# CSV — for spreadsheets and data processing
mantecato pages --site kerykeion.net --format csv > pages.csv
```

## Examples

```bash
# Overview of a site for the last 30 days
mantecato stats --site kerykeion.net

# Top 10 pages this week in JSON
mantecato pages --site kerykeion.net --period 7d --limit 10 --format json

# US traffic only, by browser
mantecato devices --site kerykeion.net --dimension browser --filter country:eq:US

# Compare this month vs last month
mantecato compare --site kerykeion.net --period this_month

# Funnel: home → docs → examples
mantecato funnel --site kerykeion.net --steps "/,/content/docs,/content/examples"

# Export all pages to CSV
mantecato pages --site kerykeion.net --limit 1000 --format csv > pages.csv

# Session replay
mantecato sessions --site kerykeion.net --period 7d --limit 1
mantecato session-activity --site kerykeion.net --session-id <uuid-from-above>
```
