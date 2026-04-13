Analyze a conversion funnel for the site and steps specified in $ARGUMENTS (format: `<site> <step1>,<step2>,<step3>,...`, e.g. `kerykeion.net /,/pricing,/signup,/welcome`).

Parse the arguments: the first word is the site, the rest (after the space) is the comma-separated step list.

Run these commands using `cd cli && uv run mantecato <command>`:

## Step 1: Run the funnel

- `funnel --site <site> --steps "<steps>" --period 30d --format json`
- `stats --site <site> --period 30d --format json`

## Step 2: Analyze each drop-off point

For each step where there's a significant drop-off (>30%), investigate:

- `page-detail --site <site> --url <step_url> --period 30d --format json` (referrers, next pages, time distribution)
- `engagement --site <site> --period 30d --filter url_path:eq:<step_url> --format json` (time spent on the page)

## Step 3: Segment by dimension

For the step with the largest drop-off, run in parallel:
- `funnel --site <site> --steps "<steps>" --period 30d --filter device:eq:mobile --format json`
- `funnel --site <site> --steps "<steps>" --period 30d --filter device:eq:desktop --format json`

If there's a significant mobile/desktop difference, also check:
- `devices --site <site> --period 30d --dimension browser --filter url_path:eq:<worst_step> --format json`

## Step 4: Source quality through the funnel

For the first step in the funnel:
- `sources --site <site> --period 30d --filter url_path:eq:<first_step> --limit 10 --format json`

Cross-reference: do users from certain sources convert better through the funnel?

## Step 5: Trend

- `funnel --site <site> --steps "<steps>" --period 7d --format json` (recent week)
- Compare with the 30d funnel to see if conversion is improving or declining.

## Output format

1. **Executive Summary** — Overall conversion rate and the biggest bottleneck.
2. **Funnel Visualization** — ASCII funnel showing each step, visitors, and drop-off %.
   ```
   Step 1: /            2,450 visitors (100%)
                           ↓  62% continue
   Step 2: /pricing       1,519 visitors (62%)
                           ↓  28% continue
   Step 3: /signup          425 visitors (17%)  ← biggest drop-off
                           ↓  71% continue
   Step 4: /welcome         302 visitors (12%)
   ```
3. **Drop-off Analysis** — For each significant drop-off: what's happening on that page, where users go instead, how long they spend.
4. **Segment Comparison** — Mobile vs desktop conversion rates at each step.
5. **Source Impact** — Which traffic sources produce the best funnel conversion.
6. **Trend** — Is the funnel improving or degrading vs the previous period?
7. **Recommendations** — Ranked by potential impact: what to fix at each step.

Include actual numbers and percentages at every step.
