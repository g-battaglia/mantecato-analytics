# CLI analytics requirements

Status: proposed, amended by the remote-client architecture below

## Architecture amendment

The native Django/DB CLI and the public Python SDK described later in this file are
superseded. The supported clients are two independent distributions:

- `mantecato-cli`, command `mantecato`;
- `mantecato-mcp`, command `mantecato-mcp`.

Both clients use HTTPS, the REST API and an existing `mtk_...` API key. They do not
install Django, import server modules or connect to PostgreSQL. The Python SDK is
removed. Shared analytics behavior lives in additive `/api/v1/` server endpoints;
the existing dashboard, legacy API, management commands, core query engine and
tracker remain unchanged. Requirements below that mention direct database access,
`cli/mantecato_cli/`, SDK parity or server bootstrap must be interpreted through
this amendment. CLI safety checks apply to HTTP requests, while the new API handlers
enforce query timeouts, cardinality limits and read-only analytics transactions.

## 1. Purpose

Mantecato's CLI already exposes the core analytics queries and is useful for routine inspection. It is not yet sufficient for diagnosing a traffic change without writing SQL against the production database.

A typical investigation needs to answer all of the following:

- Is the change real, or is it caused by a partial day or a different weekday?
- Which countries, sources, pages, sections, or content groups account for it?
- How do the current and comparison periods differ in absolute and percentage terms?
- Does the change concern pageviews, daily unique visitors, or visits?
- Is unusual automated traffic distorting the result?

The CLI must support this analysis directly while preserving Mantecato's privacy model and metric semantics.

## 2. Scope

This requirement covers the independent `mantecato-cli` package and the additive API v1 query services needed by it.

It adds:

1. explicit date boundaries;
2. safe handling of partial periods;
3. dimensioned time series;
4. period-over-period breakdowns;
5. ranked deltas for pages, sections, groups, sources, devices, geo, and events;
6. reusable segments;
7. traffic-quality diagnostics;
8. clearer visitor metric names and metadata;
9. machine-readable, stable output;
10. connection and configuration diagnostics.

The same query capability must be exposed through the REST API, CLI and MCP server. There is no public Python SDK.

## 3. Non-goals

This work must not add or infer:

- persistent user identities;
- cross-day user journeys;
- returning-visitor tracking;
- fingerprinting;
- full IP addresses or raw user agents;
- city or region data;
- automatic claims that a visitor is a bot when only an anomaly has been detected;
- an unrestricted SQL interface;
- write operations in analytics inspection commands.

The implementation must operate on the dimensions Mantecato already stores.

## 4. Terminology and metric semantics

The CLI must use these terms consistently:

- `pageviews`: pageview events in the requested interval.
- `daily_unique_visitors`: unique visitors calculated within each UTC day and summed when the result spans multiple days. Mantecato does not deduplicate across days.
- `visits`: sessions calculated with Mantecato's existing inactivity-gap logic. When a time series is requested, the value belongs to the individual bucket.
- `bot_pageviews`: pageviews whose stored `is_bot` value is true.
- `human_pageviews`: pageviews whose stored `is_bot` value is false. This means "not classified as a bot", not guaranteed human traffic.
- `current`: the period being investigated.
- `previous`: the comparison period.
- `elapsed alignment`: truncating a comparison period to the same elapsed duration as an incomplete current period.

Existing output fields may remain temporarily for backward compatibility, but new output must expose unambiguous names and metric metadata.

## 5. Shared date-range options

### 5.1 Explicit boundaries

Every read-only analytics command that currently accepts `--range` must also accept:

```text
--start <ISO-8601 date or timestamp>
--end <ISO-8601 date or timestamp>
--timezone <IANA timezone or UTC>
```

Examples:

```bash
mantecato timeseries -w <uuid> \
  --start 2026-09-10 \
  --end 2026-09-17 \
  --timezone UTC

mantecato stats -w <uuid> \
  --start 2026-09-17T00:00:00Z \
  --end 2026-09-19T00:00:00Z
```

Requirements:

- `--start` and `--end` must be supplied together.
- Explicit boundaries take precedence over `--range`.
- A date-only `--end` is an exclusive boundary. `--end 2026-09-19` means data before `2026-09-19T00:00:00` in the selected timezone.
- Timestamp boundaries are also treated as a half-open interval: `[start, end)`.
- Existing preset behavior remains backward compatible.
- Invalid or reversed boundaries exit with code 2 and a specific error.
- Output metadata includes resolved UTC boundaries, selected timezone, and whether the end is partial.

Half-open intervals are required to avoid double counting adjacent periods.

### 5.2 Complete-period controls

Add:

```text
--exclude-partial-bucket
--include-partial-bucket
```

For daily granularity, `--exclude-partial-bucket` removes the current incomplete day. The default remains backward compatible, but JSON metadata must identify incomplete buckets.

### 5.3 Elapsed-period alignment

Comparison commands must support:

```text
--align full
--align elapsed
```

- `full` compares complete requested intervals.
- `elapsed` truncates the comparison interval to the same elapsed duration as the current interval.

Example: at 10:53 UTC, `today` compared with `previous_week` under `--align elapsed` compares both Saturdays from 00:00 through 10:53 UTC.

The CLI must reject `--align elapsed` if the periods cannot be aligned deterministically.

## 6. Dimensioned time series

Extend `timeseries` with repeatable or comma-separated dimensions:

```text
--dimension <name>
```

Examples:

```bash
mantecato timeseries -w <uuid> -r 30d -g day \
  --dimension country \
  --filter 'country:in:US,GB,CA,AU'

mantecato timeseries -w <uuid> -r 7d -g day \
  --dimension country,referrer_domain
```

Supported dimensions:

- `country`
- `referrer_domain`
- `browser`
- `os`
- `device`
- `hostname`
- `url_path`
- `page_title`
- `event_name`, for event queries
- `content_group`

Requirements:

- Zero dimensions preserve the current aggregated behavior.
- One dimension is required for the first release.
- Two dimensions should be supported where query cardinality remains bounded.
- More than two dimensions must be rejected unless an explicit future limit changes this requirement.
- Results are grouped by time bucket and requested dimensions.
- `content_group` expands the stored JSON list. Since one page can have multiple groups, group rows can overlap and must not be summed as a site total.
- The output includes a `rows_are_overlapping` metadata flag for `content_group`.
- Missing values are represented consistently as `(direct)`, `(not set)`, or another documented stable sentinel.
- JSON must use `null` for an absent raw dimension and may include a separate display label.
- The command must support `--limit` for high-cardinality dimensions and report whether results were truncated.

## 7. Period comparison breakdown

Add a new command:

```text
mantecato compare-breakdown
```

Minimum interface:

```bash
mantecato compare-breakdown -w <uuid> \
  --dimension country \
  --current-start 2026-09-17 \
  --current-end 2026-09-19 \
  --previous-start 2026-09-10 \
  --previous-end 2026-09-12 \
  --metric pageviews \
  --filter 'country:in:US,GB,CA,AU'
```

It must also support derived comparison presets:

```text
--current-range today|yesterday|7d|14d|30d|this_week|...
--compare previous_period|previous_week|previous_year
--align full|elapsed
```

Supported dimensions match section 6. Supported metrics must include:

- `pageviews`
- `daily_unique_visitors`
- `visits`
- `bounces`
- `bounce_rate`
- `total_duration`
- `average_visit_duration`
- `pages_per_visit`
- `events`, when the dimension or command concerns custom events

Each row must contain:

```json
{
  "dimension": "US",
  "current": 3702,
  "previous": 4250,
  "absolute_change": -548,
  "percentage_change": -12.9,
  "share_of_current": 81.7,
  "contribution_to_total_change": 85.1
}
```

Rules:

- `percentage_change` is `null` when the previous value is zero.
- `contribution_to_total_change` is `null` when the total change is zero.
- Percentage calculations use unrounded values.
- Table rendering may round values, but JSON retains stable numeric types.
- Sorting options must include `current`, `previous`, `absolute_change`, `percentage_change`, and `contribution`.
- Add `--direction gains|losses|both`.
- Add `--minimum-current`, `--minimum-previous`, and `--minimum-total` to suppress noise from tiny rows.
- Totals are calculated independently and are not obtained by summing overlapping content groups.

## 8. Ranked delta support on existing commands

The following commands must accept a comparison period:

- `top-pages`
- `top-sections`
- `top-groups`
- `events`
- `devices`
- `geo`
- `sources`

Suggested syntax:

```bash
mantecato top-pages -w <uuid> -r 7d \
  --compare previous_week \
  --sort absolute_change \
  --direction losses

mantecato top-groups -w <uuid> -r 7d \
  --group-prefix 'family:' \
  --compare previous_period \
  --filter 'country:in:US,GB,CA,AU'
```

Requirements:

- Existing output without `--compare` remains unchanged.
- Comparison output uses the schema in section 7.
- `top-groups` adds `--group-prefix` and `--group-exact` selectors.
- The command reports rows present in only one of the periods.
- Ranking happens after both periods are joined, so a page that fell to zero remains visible.
- The query must not select only the current top N before joining. Doing so would hide complete losses.

## 9. Reusable segments

Add named segments so frequently used filters do not need to be repeated.

Example configuration:

```yaml
segments:
  tier1_en:
    filters:
      - country:in:US,GB,CA,AU
  organic_tier1:
    filters:
      - country:in:US,GB,CA,AU
      - referrer_domain:in:google.com,bing.com,duckduckgo.com
```

CLI usage:

```bash
mantecato timeseries -w <uuid> -r 30d --segment tier1_en
```

Requirements:

- Support a user configuration file and an explicit `--config` path.
- Document the default configuration path for Linux, macOS, and Windows.
- `--segment` filters are combined with explicit `--filter` values using AND semantics.
- The resolved filters appear in JSON metadata.
- Unknown segments exit with code 2 and list available segment names.
- Segment definitions contain filters only. They must not contain arbitrary SQL or executable code.

## 10. Traffic-quality diagnostics

Add:

```text
mantecato traffic-quality
```

Example:

```bash
mantecato traffic-quality -w <uuid> -r 7d \
  --dimension country \
  --limit 30
```

For each row, report where available:

- pageviews;
- daily unique visitors;
- visits;
- pageviews per visit;
- pageviews per daily unique visitor;
- bounce rate;
- direct-traffic share;
- one-page-visit share;
- stored bot pageviews and stored bot share;
- dominant browser and its share;
- dominant device and its share;
- change from the selected comparison period;
- anomaly indicators.

Anomaly indicators may identify conditions such as:

- unusually high pageviews per visitor;
- unusually high one-page share;
- sudden volume change;
- one browser/device combination dominating a row;
- a large discrepancy between suspicious behavior and stored `is_bot` classification.

Requirements:

- Indicators are diagnostic, not a replacement for `is_bot`.
- Use labels such as `high_pages_per_visitor` or `single_browser_concentration`, not `bot` unless the stored classifier marked the events as bots.
- Thresholds must be documented and configurable.
- JSON exposes the measured value, threshold, and indicator name.
- The command must explain that cookieless visitor counting can merge visitors on shared masked networks.
- No new personal data may be collected or retained for this feature.

## 11. Filters

The CLI must document and consistently support all stored filter dimensions:

- `url_path`
- `page_title`
- `hostname`
- `browser`
- `os`
- `device`
- `country`
- `event_name`
- `referrer_domain`
- `content_group`
- `is_bot`

Supported operators:

- `eq`
- `neq`
- `contains`
- `not_contains`
- `starts_with`
- `not_starts_with`
- `in`
- `not_in`

Requirements:

- `in` and `not_in` accept comma-separated values with escaping or repeated values.
- Invalid columns and operators exit with code 2 and list valid choices.
- Filter validation is authoritative in API v1 and produces equivalent behavior in CLI and MCP.
- JSON metadata contains normalized filters.
- Secrets or connection strings must never appear in emitted metadata.

## 12. Output contract

All new commands support:

```text
--format table|json|csv
```

### 12.1 JSON

JSON is the stable automation format. It must have this top-level structure:

```json
{
  "schema_version": "1",
  "query": {
    "website_id": "...",
    "start": "2026-09-17T00:00:00Z",
    "end": "2026-09-19T00:00:00Z",
    "timezone": "UTC",
    "granularity": "day",
    "dimensions": ["country"],
    "metrics": ["pageviews"],
    "filters": ["country:in:US,GB,CA,AU"],
    "partial": false,
    "truncated": false
  },
  "comparison": null,
  "totals": {},
  "rows": []
}
```

Requirements:

- Numeric values are JSON numbers, not formatted strings.
- Dates and timestamps use ISO 8601.
- Field names remain stable within a schema version.
- Additive changes require no schema bump. Renames or semantic changes do.
- Diagnostic messages and framework warnings go to stderr, never stdout.
- A successful JSON command writes valid JSON even when no rows match.

### 12.2 CSV

- CSV includes one header row.
- Timestamps use ISO 8601.
- Null values are empty fields.
- Metadata that does not fit row form is omitted or written only when an explicit sidecar option is requested.

### 12.3 Table

- Tables use human-readable labels and aligned columns.
- A partial current period is visibly marked.
- Overlapping content-group rows display a warning below the table.
- Values may be formatted for readability, but their meaning must match JSON.

## 13. Connection and runtime diagnostics

Add:

```text
mantecato doctor
```

It must check without modifying data:

- local URL and credential configuration;
- TLS and server reachability;
- API-key authentication;
- website existence and accessibility;
- API v1 capability and schema version;
- output-channel integrity for JSON mode.

Database, migration and Django-setting checks are server concerns and are not exposed
to a read-scoped remote client.

Requirements:

- Secrets are redacted.
- Exit code 0 means all required checks passed.
- Exit code 1 means a runtime dependency failed.
- Exit code 2 means invalid CLI usage.
- Warnings such as open `ALLOWED_HOSTS` or proxy configuration should not pollute analytics JSON output. They may appear in `doctor` or on stderr.

## 14. Read-only safety

Analytics commands must be safe to run against production.

Requirements:

- The documentation recommends a read-scoped API key for CLI analytics.
- New server-side analytics handlers execute inside bounded read-only transactions where supported.
- Commands must apply statement timeouts.
- High-cardinality queries must have a configurable maximum row count.
- Two-dimensional queries must estimate or bound cardinality before executing.
- The CLI must require an explicit `--allow-large-query` override when a query exceeds the safe threshold.
- Cancellation with Ctrl-C must cancel the active database query where possible.
- No analytics command may run migrations or perform writes as a side effect of bootstrap.

## 15. Performance requirements

For a website with up to 10 million events in the selected range:

- a one-dimensional, seven-day daily time series should normally complete within 5 seconds on the supported production database profile;
- a period comparison over a bounded top dimension should normally complete within 10 seconds;
- commands must stream or page large outputs rather than loading unbounded results into memory;
- content-group expansion must use PostgreSQL JSON operations or another bounded query strategy, not an unbounded Python scan of all matching rows;
- current and previous periods should be queried together when this reduces scans;
- query plans must use existing website/date/type indexes where applicable.

Performance targets are operational targets, not reasons to return incorrect or silently truncated data.

## 16. Privacy requirements

All additions must preserve the existing privacy design:

- no new event fields are required;
- no raw IP address or user agent is queried or displayed;
- country remains the most precise geographic dimension;
- visitor data is aggregate only;
- content groups remain page metadata;
- results must respect visitor-key retention and aggregate fallback behavior;
- filtered visitor metrics must be reported only when the query engine can calculate them correctly;
- if a metric is unavailable for a filter or historical range, return `null` plus a machine-readable reason instead of zero.

Suggested unavailable-metric form:

```json
{
  "value": null,
  "unavailable_reason": "historical_aggregate_not_filterable"
}
```

## 17. Backward compatibility

- Existing commands and aliases remain available.
- Existing preset names retain their meaning.
- Existing table output should remain unchanged when no new option is used, unless a documented correctness issue requires a change.
- Existing JSON consumers need a deprecation period before ambiguous visitor fields are removed.
- Deprecated fields emit warnings on stderr only.
- Shared CLI options belong in the independent `packages/mantecato-cli` package rather than server modules.

## 18. API, CLI, and MCP parity

The underlying service/query layer must not be CLI-specific.

The following capabilities should be reusable by all programmatic interfaces:

- explicit half-open ranges;
- dimensioned time series;
- comparison breakdowns;
- ranked deltas;
- elapsed alignment;
- traffic-quality diagnostics;
- normalized query metadata.

Interface-specific authentication and rendering remain outside the query layer.

## 19. Test requirements

### 19.1 Unit tests

Cover:

- explicit date and timestamp parsing;
- timezone conversion and daylight-saving transitions;
- half-open boundaries;
- partial-bucket detection;
- elapsed alignment;
- percentage and contribution calculations;
- zero-baseline comparison rows;
- pages present in only one period;
- content-group overlap metadata;
- filter validation;
- segment resolution;
- stable JSON serialization;
- unavailable filtered metrics;
- exit codes.

### 19.2 Query tests

Seed deterministic data covering:

- multiple countries and days;
- multiple visits per visitor;
- session gaps crossing bucket boundaries;
- direct and referred traffic;
- classified and unclassified bots;
- pages that fall to zero in the current period;
- content carrying multiple groups;
- null dimension values;
- current and historical data across visitor-key retention.

Assert that totals are calculated independently from limited or overlapping rows.

### 19.3 CLI integration tests

Run the installed command and verify:

- table, JSON, and CSV output;
- stdout contains no warnings in JSON mode;
- invalid ranges and filters return exit code 2;
- database failures return exit code 1;
- Ctrl-C and timeout behavior;
- existing command invocations remain compatible.

### 19.4 Performance tests

Add representative query-plan or benchmark tests for:

- daily country time series;
- page delta comparison;
- content-group delta comparison;
- traffic-quality country breakdown.

## 20. Acceptance scenarios

The feature is complete when all of these scenarios can be performed without direct SQL.

### Scenario A: four-country weekly trend

```bash
mantecato timeseries -w <uuid> \
  --start 2026-09-03 --end 2026-09-17 \
  --granularity day \
  --dimension country \
  --filter 'country:in:US,GB,CA,AU' \
  --format json
```

The result separates each country by day and includes pageviews, daily unique visitors, and visits.

### Scenario B: same weekdays week over week

```bash
mantecato compare-breakdown -w <uuid> \
  --dimension country \
  --current-start 2026-09-17 --current-end 2026-09-19 \
  --previous-start 2026-09-10 --previous-end 2026-09-12 \
  --filter 'country:in:US,GB,CA,AU'
```

The result shows current, previous, absolute change, percentage change, and contribution for each country.

### Scenario C: content families responsible for a decline

```bash
mantecato top-groups -w <uuid> \
  --start 2026-09-17 --end 2026-09-19 \
  --compare-start 2026-09-10 --compare-end 2026-09-12 \
  --group-prefix 'family:' \
  --filter 'country:in:US,GB,CA,AU' \
  --direction losses
```

Groups that fell to zero remain present. The result warns that group rows can overlap.

### Scenario D: partial Saturday comparison

```bash
mantecato compare-breakdown -w <uuid> \
  --dimension country \
  --current-range today \
  --compare previous_week \
  --align elapsed \
  --filter 'country:in:US,GB,CA,AU'
```

Both periods cover the same elapsed UTC duration.

### Scenario E: suspicious country traffic

```bash
mantecato traffic-quality -w <uuid> -r 7d \
  --dimension country \
  --compare previous_period
```

The output distinguishes stored bot classification from behavioral anomaly indicators.

## 21. Suggested implementation order

1. Introduce a shared explicit-range parser and query metadata object.
2. Standardize half-open range handling in the query layer.
3. Add one-dimensional time series.
4. Add `compare-breakdown` for one dimension.
5. Add comparison support to ranked commands.
6. Add content-group prefix selection and overlap metadata.
7. Add elapsed alignment.
8. Add reusable segments.
9. Add traffic-quality diagnostics.
10. Expose the same query capabilities through API, the independent CLI, and MCP.
11. Deprecate ambiguous visitor field names after consumers have migrated.

## 22. Definition of done

This requirement is complete when:

- every acceptance scenario passes without SQL or a Django shell;
- all new commands support table, JSON, and CSV;
- JSON output follows the documented schema and contains no stdout noise;
- date boundaries and comparison semantics are covered by tests;
- privacy constraints are unchanged;
- production queries are bounded and read-only;
- existing CLI invocations remain compatible;
- REST API, CLI, and MCP parity is delivered or tracked explicitly, with no analytics calculations implemented only in a client;
- user documentation includes examples for explicit ranges, country groups, page/group deltas, partial-day alignment, and traffic-quality interpretation.
