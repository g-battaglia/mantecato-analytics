# Claude Code Commands

Slash commands available in `.claude/commands/`. Invoke with `/<name> <arguments>`.

## Available Commands

| Command | Arguments | Purpose |
|---------|-----------|---------|
| `/analytics` | `<site> [period]` | Comprehensive site analysis with cross-referencing |
| `/traffic-report` | `<site> <period>` | Full traffic report (sources, content, audience) |
| `/content-audit` | `<site> <period>` | Content performance audit (scorecard, problem pages) |
| `/funnel-analysis` | `<site> <steps>` | Conversion funnel analysis with segment breakdown |

## Usage Examples

```
/analytics kerykeion.net 30d
/traffic-report kerykeion.net 90d
/content-audit kerykeion.net 60d
/funnel-analysis kerykeion.net /,/pricing,/signup,/welcome
```

## How Commands Work

Each command is a markdown file that instructs Claude to:
1. Run CLI queries in parallel (`cd cli && uv run mantecato <command> --format json`)
2. Analyze the JSON results
3. Present findings in a structured format with real numbers and deltas

## Analysis Methodology

1. **Start with context** — `report` or `stats` + `compare` for the big picture
2. **Go wide, then deep** — High-level breakdowns first, then drill into anomalies
3. **Use JSON for computation** — `--format json` for analysis, `--format table` for presentation
4. **Cross-reference dimensions** — Combine filters to find insights (e.g. mobile + organic)
5. **Always compare periods** — Contextualize with period-over-period deltas
6. **Increase limits** — Use `--limit 50` or `--limit 100` for comprehensive data
7. **Run in parallel** — Independent commands should run concurrently
