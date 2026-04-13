Produce a comprehensive traffic report for the site and period specified in $ARGUMENTS (format: `<site> <period>`, e.g. `kerykeion.net 30d`).

Run these commands using `cd cli && uv run mantecato <command>`:

## Step 1: Overall metrics and trends

Run in parallel:
- `stats --site <site> --period <period> --format json`
- `compare --site <site> --period <period> --format json`
- `timeseries --site <site> --period <period> --granularity day --format json`

## Step 2: Traffic breakdown

Run in parallel:
- `top-pages --site <site> --period <period> --limit 20 --format json`
- `sources --site <site> --period <period> --limit 20 --format json`
- `channels --site <site> --period <period> --format json`
- `devices --site <site> --period <period> --format json`
- `geo --site <site> --period <period> --limit 10 --format json`

## Step 3: Quality analysis

Run in parallel:
- `engagement --site <site> --period <period> --format json`
- `devices --site <site> --period <period> --dimension browser --format json`
- `devices --site <site> --period <period> --dimension os --format json`

## Step 4: Cross-reference (pick 2-3 based on findings)

Use filters to investigate anomalies found in steps 1-3. Examples:
- `stats --site <site> --period <period> --filter device:eq:mobile --format json` (mobile quality)
- `pages --site <site> --period <period> --filter country:eq:<top_country> --limit 10 --format json`
- `sources --site <site> --period <period> --filter device:eq:desktop --format json`

## Output format

Deliver the report as:

1. **Executive Summary** — 2-3 sentences. Lead with the most important finding.
2. **Key Metrics** — table with metric, current value, previous value, and % change.
3. **Traffic Sources** — breakdown by channel with quality metrics (bounce rate, pages/visit).
4. **Content Performance** — top pages, pages gaining/losing traffic, high bounce rate pages.
5. **Audience** — device split, geographic distribution, browser/OS highlights.
6. **Engagement** — session duration distribution, percentiles, bounce rate trends.
7. **Recommendations** — 3-5 specific, actionable next steps based on the data.

Always include actual numbers with deltas. Never say "traffic increased" — say "traffic increased 23% (1,240 → 1,525 visitors)."
