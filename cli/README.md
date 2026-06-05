# Mantecato CLI

Command-line interface for Mantecato, built with Typer + Rich.
Provides access to all analytics features, resource CRUD operations, and
direct queries to the analytics engine, with output in table, JSON, or CSV format.

## Installation

```bash
# From the project root
pip install -e ".[cli]"

# Or directly from the CLI directory
cd cli/
pip install -e .
```

## Configuration

The CLI operates in local mode, querying the PostgreSQL database directly
through Django. The required environment variables are the same as for
the web server:

```bash
# In .env or as environment variables
DATABASE_URL=postgresql://user:pass@localhost:5432/mantecato
SECRET_KEY=your-secret-key
```

## Usage

```bash
mantecato --help
```

All commands that return data accept the `--format` option:

```bash
mantecato overview -w <uuid> --format json
mantecato overview -w <uuid> --format table   # default
mantecato overview -w <uuid> --format csv
```

## Command Groups

### Analytics (15 commands)

High-level commands that call the same service functions as the web dashboard.

```bash
# List sites
mantecato sites

# Site overview (last 30 days, default)
mantecato overview -w <website-uuid>
mantecato overview -w <uuid> -r 7d

# Top pages
mantecato pages -w <uuid> -r 30d --page 1

# Traffic sources
mantecato sources -w <uuid>

# Custom events
mantecato events -w <uuid> -r 7d

# Sessions (paginated list)
mantecato sessions -w <uuid> --page 2

# Device breakdown
mantecato devices -w <uuid>

# Geographic distribution with drill-down
mantecato geo -w <uuid>
mantecato geo -w <uuid> --country IT
mantecato geo -w <uuid> --country IT --region 25

# Period comparison
mantecato compare -w <uuid> --mode previous_period
mantecato compare -w <uuid> --mode previous_year

# Cohort retention
mantecato retention -w <uuid> --granularity week

# Conversion funnels
mantecato funnels -w <uuid> --window 60

# User journeys
mantecato journeys -w <uuid> --path-length 4 --limit 10

# Revenue
mantecato revenue -w <uuid>

# Engagement
mantecato engagement -w <uuid>

# Real-time
mantecato realtime -w <uuid>
```

### CRUD

Management of dashboards, API keys, scheduled exports, and bot config.

```bash
# Dashboards
mantecato dashboards -u <user-uuid>
mantecato dashboard <report-uuid> -u <user-uuid>
mantecato dashboard-create -u <user-uuid> -w <website-uuid> -n "Sales Dashboard"
mantecato dashboard-delete <report-uuid> -u <user-uuid>

# API keys
mantecato api-keys -u <user-uuid>
mantecato api-key-create -u <user-uuid> -n "CI/CD key"
mantecato api-key-delete <key-uuid> -u <user-uuid>

# Annotations
mantecato annotations -u <user-uuid> -w <website-uuid>
mantecato annotation-create -u <user-uuid> -w <website-uuid> -t "Deploy v2" -d 2024-06-15
mantecato annotation-delete <report-uuid> -u <user-uuid>

# Bot config
mantecato bot-config -w <website-uuid>

# Scheduled exports
mantecato scheduled-exports -u <user-uuid>
mantecato scheduled-export <report-uuid> -u <user-uuid>
mantecato scheduled-export-delete <report-uuid> -u <user-uuid>
```

### Direct Queries (17 commands)

Direct access to the SQL query engine. Useful for advanced analysis and scripting.
Support repeatable `--filter` and aliases `--site/-s` and `--period/-p`.

```bash
# Aggregate statistics
mantecato stats -w <uuid> -r 30d

# Time series
mantecato timeseries -w <uuid> -r 7d -g day
mantecato timeseries -w <uuid> -r 90d -g week

# Top pages with mode
mantecato top-pages -w <uuid> -l 50 --mode path
mantecato top-pages -w <uuid> --mode title

# URL sections aggregated by depth
mantecato top-sections -w <uuid> --depth 2

# Top referrers
mantecato top-referrers -w <uuid> -l 10

# Top events (with or without properties)
mantecato top-events -w <uuid>
mantecato top-events -w <uuid> --properties

# Page detail: referrers, next pages, time distribution, time series
mantecato page-detail -w <uuid> --url /pricing

# Referrers for a page
mantecato page-referrers -w <uuid> --url /

# Next pages after a URL
mantecato next-pages -w <uuid> --url /

# Event detail: time series and properties
mantecato event-detail -w <uuid> --event signup

# Single event time series
mantecato event-timeseries -w <uuid> --event purchase -g day

# Event properties
mantecato event-properties -w <uuid> --event signup

# Full session activity
mantecato session-activity -w <uuid> --session-id <session-uuid>

# Aggregated traffic channels
mantecato channels -w <uuid>

# UTM breakdown
mantecato utm -w <uuid> --dimension utm_source
mantecato utm -w <uuid> --dimension utm_campaign -l 50

# Click IDs (gclid, fbclid, ...)
mantecato clickids -w <uuid>

# Hostname breakdown
mantecato hostnames -w <uuid>

# Pages by referrer
mantecato referrer-pages -w <uuid> --referrer google.com

# Available values for a filter
mantecato filter-values -w <uuid> --column country --search it

# Traffic heatmap by hour/day
mantecato heatmap -w <uuid> --timezone Europe/Rome
```

### Filters

Query commands accept repeatable `--filter` to filter data:

```bash
mantecato stats -w <uuid> --filter country:IT --filter browser:Chrome
mantecato top-pages -w <uuid> --filter os:iOS --filter device:mobile
```

## Common Options

| Option | Alias | Description | Default |
|---|---|---|---|
| `--website` | `-w` | Website UUID | required |
| `--range` | `-r` | Date range preset (`7d`, `30d`, `90d`, `today`, `12mo`, ...) | `30d` |
| `--format` | | Output format: `json`, `table`, `csv` | `table` |
| `--user` | `-u` | User UUID (CRUD commands) | required |
| `--limit` | `-l` | Maximum number of rows | `20` |
| `--filter` | | Filter expression (repeatable) | none |

## Code Structure

```
cli/
  mantecato_cli/
    app.py             Root Typer definition, shared options, helpers
    main.py            Entry point, Django bootstrap
    helpers.py         Output formatting (table, json, csv)
    bootstrap.py       Django settings setup
    commands/
      analytics.py     15 analytics commands (overview, pages, sources, ...)
      crud.py          CRUD commands (dashboard, API key, bot config, ...)
      queries.py       17 direct query commands (stats, timeseries, top-pages, ...)
```
