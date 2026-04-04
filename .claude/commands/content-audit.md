Audit content performance for the site and period specified in $ARGUMENTS (format: `<site> <period>`, e.g. `kerykeion.net 90d`).

Run these commands using `python -m backend.app.cli.main <command>`:

## Step 1: Page inventory

Run in parallel:
- `pages --site <site> --period <period> --limit 100 --format json`
- `top-pages --site <site> --period <period> --limit 50 --format json`
- `stats --site <site> --period <period> --format json`

## Step 2: Identify problem pages

From the pages data, identify:
- **High bounce rate pages** (bounce rate > 70%)
- **Low engagement pages** (avg time-on-page < 10s)
- **Entry pages with high exit rate** (entry_rate > 10% AND exit_rate > 60%)
- **Pages with declining traffic** (compare with previous period)

For the top 5 problem pages, run:
- `page-detail --site <site> --url <path> --period <period> --format json`

## Step 3: Source quality per page

For the top 3 highest-traffic pages:
- `sources --site <site> --period <period> --filter url_path:eq:<path> --format json`

For the top 3 highest-bounce pages:
- `sources --site <site> --period <period> --filter url_path:eq:<path> --format json`

## Step 4: Content by audience segment

Run in parallel:
- `pages --site <site> --period <period> --filter device:eq:mobile --limit 20 --format json`
- `pages --site <site> --period <period> --filter device:eq:desktop --limit 20 --format json`

Compare mobile vs desktop performance for the same pages.

## Step 5: Trends

- `compare --site <site> --period <period> --format json`
- If period is 90d+, run `timeseries --site <site> --period <period> --granularity week --format json` to spot content trends.

## Output format

1. **Executive Summary** — Overall content health in 2-3 sentences.
2. **Content Scorecard** — Table with: Page, Views, Bounce Rate, Avg Time, Entry %, Exit %, Verdict (strong/weak/critical).
3. **Top Performers** — Pages doing well and why (good sources? high engagement?).
4. **Underperformers** — Pages with problems and diagnosed causes.
5. **Mobile vs Desktop** — Pages where mobile experience differs significantly.
6. **Source-Content Fit** — Which sources send the right audience to which content.
7. **Recommendations** — Ranked list: what to fix, what to promote, what to retire.

Include actual numbers. Compare against site averages to contextualize.
