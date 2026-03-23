---
description: Analyze a conversion funnel to identify drop-off points, segment by device and source, and recommend optimizations. Produces a step-by-step funnel visualization with drop-off analysis and actionable fixes.
---

# Funnel Analysis

Analyze a conversion funnel using the Mantecato CLI. The user will specify a site and funnel steps (e.g. "kerykeion.net /,/pricing,/signup,/welcome").

## Running Commands

Always use:
```bash
npx tsx src/cli/index.ts <command> [options]
```

The working directory is the mantecato project root. `DATABASE_URL` and `MANTECATO_API_KEY` are already configured.

## Workflow

### Step 1: Run the funnel

Run in parallel:
- `funnel --site <site> --steps "<comma-separated-steps>" --period 30d --format json`
- `stats --site <site> --period 30d --format json`

### Step 2: Analyze each drop-off point

For each step where there's a significant drop-off (>30%), investigate:
- `page-detail --site <site> --url <step_url> --period 30d --format json`

This reveals: referrers to that page, where users go next (instead of the expected next step), and time spent.

### Step 3: Segment by device

For the step with the largest drop-off, run in parallel:
- `funnel --site <site> --steps "<steps>" --period 30d --filter device:eq:mobile --format json`
- `funnel --site <site> --steps "<steps>" --period 30d --filter device:eq:desktop --format json`

If there's a significant mobile/desktop gap, also check:
- `devices --site <site> --period 30d --dimension browser --filter url_path:eq:<worst_step> --format json`

### Step 4: Source quality through the funnel

For the first step in the funnel:
- `sources --site <site> --period 30d --filter url_path:eq:<first_step> --limit 10 --format json`

Cross-reference: do users from certain sources convert better?

### Step 5: Trend comparison

Run in parallel:
- `funnel --site <site> --steps "<steps>" --period 7d --format json` (recent week)
- `funnel --site <site> --steps "<steps>" --period 30d --format json` (if not already done)

Compare to see if conversion is improving or declining.

## Report Format

1. **Executive Summary** — Overall conversion rate and the biggest bottleneck in 2-3 sentences.
2. **Funnel Visualization** — ASCII funnel:
   ```
   Step 1: /            2,450 visitors (100%)
                           ↓  62% continue
   Step 2: /pricing       1,519 visitors (62%)
                           ↓  28% continue
   Step 3: /signup          425 visitors (17%)  ← biggest drop-off
                           ↓  71% continue
   Step 4: /welcome         302 visitors (12%)
   ```
3. **Drop-off Analysis** — For each significant drop-off: what's happening, where users go instead, time spent on page.
4. **Segment Comparison** — Mobile vs desktop conversion at each step.
5. **Source Impact** — Which traffic sources produce the best funnel conversion.
6. **Trend** — Is the funnel improving or degrading?
7. **Recommendations** — Ranked by potential impact: what to fix at each step.

## Rules

- Include actual numbers and percentages at every step.
- Never guess data. Always run the command.
- Use `--format json` for processing.
- Run independent commands in parallel.
