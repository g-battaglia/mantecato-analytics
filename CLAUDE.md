# Mantecato — Claude Code Instructions

## Architecture

This project is no longer a Next.js monolith.

- `frontend/` contains the Vite + React SPA.
- `backend/` contains the FastAPI backend, CLI, and MCP server (all Python).

Do not add or rely on `next/*` APIs unless you are explicitly working on historical migration material.

## What This Project Is

Mantecato is a standalone analytics dashboard that reads an existing Umami PostgreSQL database. It provides a web UI, a 45-command CLI, and a 41-tool MCP server.

**You can analyze any site's traffic using the CLI.** The `DATABASE_URL` and `MANTECATO_API_KEY` environment variables are already configured.

## Running CLI Commands

```bash
uv run --project backend python -m app.cli.main <command> [options]
```

All commands support these global options:

| Option | Description | Default |
|--------|-------------|---------|
| `-s, --site <site>` | Site name, domain, or UUID (partial match works) | required |
| `-p, --period <preset>` | `1h` `3h` `6h` `today` `yesterday` `24h` `7d` `14d` `30d` `60d` `90d` `6m` `12m` `this_week` `last_week` `this_month` `last_month` `this_quarter` `last_quarter` `this_year` `last_year` `all` | `30d` |
| `--start <date>` / `--end <date>` | Custom ISO 8601 range (overrides period) | - |
| `-f, --format json\|table\|csv` | Output format | `table` |
| `--filter <col:op:val>` | Repeatable filter | - |
| `-l, --limit <n>` | Max rows | `20` |
| `-g, --granularity <g>` | `auto` `minute` `hour` `day` `week` `month` | `auto` |

## All 45 Commands

**Core:**
- `sites` — list all tracked sites
- `stats` — overview: pageviews, visitors, visits, bounce rate, avg duration, pages/visit
- `timeseries` — pageview and visitor time series
- `compare` — current vs previous period with deltas
- `report` — full analytics report in one shot: stats, comparison, top pages, sources, events with properties, channels

**Pages:**
- `pages` — page analytics: views, time-on-page, bounce rate, entries/exits
- `page-detail --url <path>` — drill-down: referrers, next pages, time distribution
- `top-pages` — quick top pages by visitors

**Sources:**
- `sources` — traffic sources with bounce rate and duration
- `referrer-pages --referrer <domain>` — pages a referrer drives traffic to
- `channels` — auto-grouped channels (Organic, Direct, Social, Paid, etc.)
- `utm` — UTM parameter breakdown
- `clickids` — click ID analysis (gclid, fbclid, etc.)
- `hostnames` — hostname breakdown
- `top-referrers` — quick top referrers

**Events:**
- `events` — custom event metrics
- `event-detail --event <name>` — time series + property breakdown
- `top-events` — quick top events

**Sessions:**
- `sessions` — session list with location, device, engagement
- `session-activity --session-id <uuid>` — full event replay

**Devices:**
- `devices` — device type breakdown (default)
- `devices --dimension browser|os|screen|language` — breakdown by dimension

**Geographic:**
- `geo` — country-level breakdown
- `geo --level region --country <CC>` — region drill-down
- `geo --level city --country <CC>` — city drill-down

**Advanced:**
- `realtime` — live active visitors
- `retention` — cohort retention analysis
- `funnel --steps "/step1,/step2,/step3"` — conversion funnel
- `journeys` — user journey paths
- `revenue` — revenue analytics
- `engagement` — duration distribution, percentiles, bounce rates
- `filter-values --column <col>` — available filter values

**CRUD (requires API key):**
- `annotations` / `annotation-create --title <t> --date <d>` / `annotation-delete --id <uuid>`
- `saved-views` / `saved-view --id <uuid>` / `saved-view-create` / `saved-view-delete --id <uuid>`
- `dashboards` / `dashboard --id <uuid>` / `dashboard-delete --id <uuid>`
- `scheduled-exports` / `scheduled-export --id <uuid>` / `scheduled-export-delete --id <uuid>`

## Filter Syntax

Format: `column:operator:value` — repeatable with `--filter`.

**Operators:** `eq`, `neq`, `contains`, `not_contains`, `starts_with`, `not_starts_with`

**Columns:** `url_path`, `page_title`, `hostname`, `referrer_domain`, `utm_source`, `utm_medium`, `utm_campaign`, `event_name`, `tag`, `browser`, `os`, `device`, `country`, `region`, `city`, `language`, `screen`

Examples:
```bash
# Full report for the last 30 days
uv run --project backend python -m app.cli.main report -s mysite.com -p 30d

# Report for mobile traffic only
uv run --project backend python -m app.cli.main report -s mysite.com -p 30d --filter device:eq:mobile

# Report for Google organic traffic only
uv run --project backend python -m app.cli.main report -s mysite.com -p 30d --filter referrer_domain:eq:google.com

# Report as JSON (for programmatic use)
uv run --project backend python -m app.cli.main report -s mysite.com -p 90d -f json

# Report for a custom date range
uv run --project backend python -m app.cli.main report -s mysite.com --start 2026-03-01 --end 2026-04-01

# Individual queries with filters
uv run --project backend python -m app.cli.main stats -s mysite.com --filter country:eq:US
uv run --project backend python -m app.cli.main pages -s mysite.com --filter device:eq:mobile --filter referrer_domain:contains:google
```

## Analysis Methodology

When asked to analyze traffic, follow this approach:

1. **Start with context.** Run `report` for a full picture in one command, or `stats` and `compare` for just the numbers.

2. **Go wide, then deep.** Start with high-level breakdowns (`top-pages`, `sources`, `devices`, `geo`), then drill into anomalies or interesting patterns.

3. **Use JSON for computation.** When you need to compute ratios, rank, or cross-reference, use `--format json`. Use `--format table` only for final presentation.

4. **Cross-reference dimensions.** The best insights come from combining data:
   - "What's the bounce rate for mobile users from organic search?"
   - "Which country has the highest pages/visit?"
   - Use filters to slice: `--filter device:eq:mobile --filter referrer_domain:contains:google`

5. **Always compare periods.** Contextualize numbers with `compare`, or run the same query with two different `--period` values.

6. **Increase limits for comprehensive data.** Use `--limit 50` or `--limit 100` when you need the full picture.

7. **Run independent commands in parallel** to save time.

## Output Format for Reports

Structure analyses as:

1. **Executive Summary** — 2-3 sentences with the key takeaway
2. **Key Metrics** — numbers that matter, with period-over-period deltas
3. **Findings** — organized by theme (traffic, engagement, sources, content)
4. **Recommendations** — specific, actionable next steps based on data

Always include actual numbers — not "traffic increased" but "traffic increased 23% (1,240 → 1,525 visitors)".

## Rules

- **Never guess data** — always run the CLI command to get real numbers
- **Always specify the period** — don't rely on defaults without stating them
- **Read-only database** — never run migrations or write to the DB directly
- **Present insights, not data dumps** — the user wants to understand what's happening and what to do about it
