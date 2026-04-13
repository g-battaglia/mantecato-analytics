# CLI

`cli/mantecato_cli/` — 45-command terminal interface. Depends on `mantecato-core`, `typer`, `rich`, `textual`.

## Running

```bash
cd cli && uv run mantecato <command> [options]
```

## Global Options

| Option | Description | Default |
|--------|-------------|---------|
| `-s, --site <site>` | Site name, domain, or UUID (partial match) | required |
| `-p, --period <preset>` | Date range preset | `30d` |
| `--start / --end` | Custom ISO 8601 range (overrides period) | — |
| `-f, --format` | `json`, `table`, `csv` | `table` |
| `--filter <col:op:val>` | Repeatable filter | — |
| `-l, --limit <n>` | Max rows | `20` |
| `-g, --granularity` | `auto`, `minute`, `hour`, `day`, `week`, `month` | `auto` |

## All 45 Commands

**Core:** sites, stats, timeseries, compare, report
**Pages:** pages, page-detail, top-pages
**Sources:** sources, referrer-pages, channels, utm, clickids, hostnames, top-referrers
**Events:** events, event-detail, top-events
**Sessions:** sessions, session-activity
**Devices:** devices (--dimension browser|os|screen|language)
**Geo:** geo (--level country|region|city, --country CC)
**Advanced:** realtime, retention, funnel, journeys, revenue, engagement, filter-values
**CRUD:** annotations, annotation-create, annotation-delete, saved-views, saved-view, saved-view-create, saved-view-delete, dashboards, dashboard, dashboard-delete, scheduled-exports, scheduled-export, scheduled-export-delete
**Config:** config get, config set, config list
**TUI:** tui

## Key Files

| File | Purpose |
|------|---------|
| `main.py` | All 44 Typer commands (~2,200 lines) |
| `report.py` | `report` command (combines stats + comparison + pages + sources + events) |
| `helpers.py` | Output formatting, async DB lifecycle |
| `tui.py` | Textual TUI dashboard |
| `config.py` | CLI config file handling (`~/.config/mantecato/config.toml`) |

## Filter Examples

```bash
uv run mantecato report -s mysite.com -p 30d --filter device:eq:mobile
uv run mantecato pages -s mysite.com --filter referrer_domain:contains:google --filter country:eq:US
uv run mantecato stats -s mysite.com -p 90d -f json
```
