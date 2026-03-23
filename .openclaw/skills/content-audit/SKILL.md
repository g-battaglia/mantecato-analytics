---
name: content-audit
description: Audit content performance for a website. Identifies top performers, underperformers, high-bounce pages, mobile vs desktop gaps, and source-content fit. Produces a content scorecard with actionable recommendations.
user-invocable: true
emoji: "📝"
---

# Content Audit

Audit content performance using the Mantecato CLI. The user will specify a site and period (e.g. "kerykeion.net 90d").

## Running Commands

Always use:
```bash
npx tsx src/cli/index.ts <command> [options]
```

The working directory is the mantecato project root. `DATABASE_URL` and `MANTECATO_API_KEY` are already configured.

## Workflow

### Step 1: Page inventory

Run in parallel:
- `pages --site <site> --period <period> --limit 100 --format json`
- `top-pages --site <site> --period <period> --limit 50 --format json`
- `stats --site <site> --period <period> --format json`

### Step 2: Identify problem pages

From the pages data, identify:
- **High bounce rate pages** — bounce rate > 70%
- **Low engagement pages** — avg time-on-page < 10 seconds
- **Leaky entry pages** — entry_rate > 10% AND exit_rate > 60%
- **Declining pages** — compare with previous period

For the top 5 problem pages, drill down:
- `page-detail --site <site> --url <path> --period <period> --format json`

### Step 3: Source quality per page

For the top 3 highest-traffic pages:
- `sources --site <site> --period <period> --filter url_path:eq:<path> --format json`

For the top 3 highest-bounce pages:
- `sources --site <site> --period <period> --filter url_path:eq:<path> --format json`

### Step 4: Mobile vs desktop content performance

Run in parallel:
- `pages --site <site> --period <period> --filter device:eq:mobile --limit 20 --format json`
- `pages --site <site> --period <period> --filter device:eq:desktop --limit 20 --format json`

Compare performance of the same pages across devices.

### Step 5: Trends

- `compare --site <site> --period <period> --format json`
- If period is 90d+: `timeseries --site <site> --period <period> --granularity week --format json`

## Report Format

1. **Executive Summary** — Overall content health in 2-3 sentences.
2. **Content Scorecard** — Table: Page | Views | Bounce Rate | Avg Time | Entry % | Exit % | Verdict (strong / weak / critical).
3. **Top Performers** — Pages doing well and why.
4. **Underperformers** — Pages with problems and diagnosed causes.
5. **Mobile vs Desktop** — Pages where mobile experience differs significantly.
6. **Source-Content Fit** — Which sources send the right audience to which content.
7. **Recommendations** — Ranked: what to fix, what to promote, what to retire.

## Rules

- Include actual numbers. Compare against site averages to contextualize.
- Never guess data. Always run the command.
- Use `--format json` for processing, increase `--limit` for comprehensive analysis.
- Run independent commands in parallel.
