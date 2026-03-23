# CLI Reference

The Mantecato CLI gives you full analytics access from the terminal. Everything you can see in the web dashboard is available as a command.

> **Note:** If you're using an AI agent (OpenCode, Claude Code, etc.), you don't need to learn these commands — the agent knows them already. This reference is here if you want to use the CLI directly or understand what the agent is doing.

## Setup

```bash
# Install (if you haven't already)
git clone https://github.com/g-battaglia/mantecato-analytics.git && cd mantecato-analytics
npm install --legacy-peer-deps
npx prisma generate

# Set your API key
export DATABASE_URL="postgresql://..."
export MANTECATO_API_KEY="mtk_your-key-here"
```

## Running Commands

```bash
# Via npm script
npm run cli -- <command> [options]

# Via npx (equivalent)
npx tsx src/cli/index.ts <command> [options]

# Via Docker
docker compose --profile cli run --rm cli <command> [options]
```

## Common Options

Every analytics command supports these:

| Option | Description | Default |
|--------|-------------|---------|
| `-s, --site <site>` | Site name, domain, or UUID | required |
| `-p, --period <preset>` | Time period: `7d`, `30d`, `90d`, `this_month`, etc. | `30d` |
| `--start <date>` | Custom start date (ISO 8601) | — |
| `--end <date>` | Custom end date (ISO 8601) | — |
| `-f, --format <format>` | Output format: `json`, `table`, `csv` | `table` |
| `--filter <filter...>` | Filter results (see [Filters](#filters) below) | — |
| `-l, --limit <n>` | Max rows to return | `20` |
| `-g, --granularity <g>` | Time grouping: `auto`, `minute`, `hour`, `day`, `week`, `month` | `auto` |
| `--api-key <key>` | API key (alternative to `MANTECATO_API_KEY` env var) | — |

The `--site` flag is flexible — all of these work:

```bash
--site kerykeion.net           # by domain
--site www.kerykeion.net       # by full domain
--site b52bd153-29af-...       # by UUID
--site kery                    # by partial name match
```

---

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
| `page-detail --url <path>` | Detailed stats for a specific page: referrers, next pages, time distribution |
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
| `devices` | Device type breakdown (default) |
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
| `filter-values --column <col>` | Available values for a filter column (useful for autocomplete) |

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

---

## Filters

Filters let you narrow down results. The format is `column:operator:value`, and you can repeat `--filter` to combine multiple conditions:

```bash
# Single filter
npm run cli -- stats --site kerykeion.net --filter country:eq:US

# Multiple filters (AND logic between different columns)
npm run cli -- stats --site kerykeion.net --filter country:eq:US --filter browser:eq:chrome
```

### Operators

| Operator | Meaning | Example |
|----------|---------|---------|
| `eq` | Equals | `country:eq:US` |
| `neq` | Not equals | `browser:neq:chrome` |
| `contains` | Contains (case-insensitive) | `url_path:contains:blog` |
| `not_contains` | Does not contain | `referrer_domain:not_contains:spam` |
| `starts_with` | Starts with | `url_path:starts_with:/docs` |
| `not_starts_with` | Does not start with | `url_path:not_starts_with:/admin` |

### Filterable columns

`url_path`, `page_title`, `hostname`, `referrer_domain`, `utm_source`, `utm_medium`, `utm_campaign`, `event_name`, `tag`, `browser`, `os`, `device`, `country`, `region`, `city`, `language`, `screen`

---

## Output Formats

```bash
# Table (default) — human-readable
npm run cli -- top-pages --site kerykeion.net

# JSON — for scripts, piping, and AI agents
npm run cli -- stats --site kerykeion.net --format json

# CSV — for spreadsheets
npm run cli -- pages --site kerykeion.net --format csv > pages.csv
```

---

## Examples

```bash
# Overview of a site for the last 30 days
npm run cli -- stats --site kerykeion.net

# Top 10 pages this week in JSON
npm run cli -- pages --site kerykeion.net --period 7d --limit 10 --format json

# US traffic only, by browser
npm run cli -- devices --site kerykeion.net --dimension browser --filter country:eq:US

# Compare this month vs last month
npm run cli -- compare --site kerykeion.net --period this_month

# Funnel: home → docs → examples
npm run cli -- funnel --site kerykeion.net --steps "/,/content/docs,/content/examples"

# Export all pages to CSV
npm run cli -- pages --site kerykeion.net --limit 1000 --format csv > pages.csv

# Session replay
npm run cli -- sessions --site kerykeion.net --period 7d --limit 1
npm run cli -- session-activity --site kerykeion.net --session-id <uuid-from-above>
```
