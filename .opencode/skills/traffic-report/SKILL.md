---
description: Generate a comprehensive traffic report for a website. Analyzes overall metrics, traffic sources, content performance, audience segments, and engagement. Produces a structured report with executive summary, findings, and recommendations.
---

# Traffic Report

Generate a full traffic report using the Mantecato CLI. The user will specify a site and period (e.g. "kerykeion.net 30d").

## Running Commands

Always use:
```bash
python -m backend.app.cli.main <command> [options]
```

The working directory is the mantecato project root. `DATABASE_URL` and `MANTECATO_API_KEY` are already configured.

## Workflow

### Step 1: Overall metrics and trends

Run in parallel:
- `stats --site <site> --period <period> --format json`
- `compare --site <site> --period <period> --format json`
- `timeseries --site <site> --period <period> --granularity day --format json`

### Step 2: Traffic breakdown

Run in parallel:
- `top-pages --site <site> --period <period> --limit 20 --format json`
- `sources --site <site> --period <period> --limit 20 --format json`
- `channels --site <site> --period <period> --format json`
- `devices --site <site> --period <period> --format json`
- `geo --site <site> --period <period> --limit 10 --format json`

### Step 3: Quality analysis

Run in parallel:
- `engagement --site <site> --period <period> --format json`
- `devices --site <site> --period <period> --dimension browser --format json`
- `devices --site <site> --period <period> --dimension os --format json`

### Step 4: Cross-reference

Based on findings from steps 1-3, investigate anomalies using filters. Examples:
- `stats --site <site> --period <period> --filter device:eq:mobile --format json`
- `pages --site <site> --period <period> --filter country:eq:<top_country> --limit 10 --format json`
- `sources --site <site> --period <period> --filter device:eq:desktop --format json`

Pick 2-3 cross-references based on what stands out in the data.

## Report Format

Structure the final report as:

1. **Executive Summary** — 2-3 sentences. Lead with the most important finding.
2. **Key Metrics** — Table with: metric, current value, previous value, % change.
3. **Traffic Sources** — Channel breakdown with quality metrics (bounce rate, pages/visit).
4. **Content Performance** — Top pages, pages gaining/losing traffic, high bounce rate pages.
5. **Audience** — Device split, geographic distribution, browser/OS highlights.
6. **Engagement** — Session duration distribution, percentiles, bounce rate trends.
7. **Recommendations** — 3-5 specific, actionable next steps grounded in the data.

## Rules

- Always include actual numbers with deltas — "traffic increased 23% (1,240 → 1,525 visitors)" not "traffic increased."
- Never guess data. Always run the command.
- Always specify the period explicitly.
- Use `--format json` for data processing, `--format table` only for final display if needed.
- Increase limits (`--limit 50`, `--limit 100`) when you need comprehensive data.
- Run independent commands in parallel.
