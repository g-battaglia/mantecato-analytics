# `core.mantecato_core` — Raw-SQL analytics query engine

The Mantecato query engine is a thin synchronous bridge over PostgreSQL for
production, with ORM fallbacks for SQLite development and tests. Analytics SQL
lives in `.py` modules under `queries/` and is executed via the Django default
database connection through the helpers in `database.py`.

This document explains the architecture, the placeholder DSL used in
every SQL string, and the public surface consumed by
`apps/analytics/services.py`.

> **Constraint**: production analytics SQL stays **raw**. SQLite fallbacks are
> intentionally limited to aggregate pageview/event reads so local pages render
> without requiring PostgreSQL.

## Layout

```
core/mantecato_core/
├── database.py       # raw_query / raw_query_one / paged_raw_query bridge
├── date_utils.py     # DateRange dataclass + preset / granularity resolution
├── filters.py        # Filter dataclass + WHERE/JOIN builder + bot-filter SQL
├── helpers.py        # CLI/MCP helpers: list_sites, parse_date_args, ...
├── types.py          # TypedDict declarations for every query return shape
└── queries/
    ├── pageviews.py      # page-level analytics
    ├── devices.py        # browser/os/device breakdown
    ├── geo.py            # country breakdown
    ├── stats.py          # high-level aggregates + top-N tables
    ├── compare.py        # period-over-period comparison
    ├── realtime.py       # live pageview counters
    ├── events.py         # custom event-name analytics
    ├── filter_values.py  # discover distinct filter values
    ├── heatmap.py        # hour-of-day / day-of-week heatmap
    ├── visitors.py       # anonymous aggregate visitor-sketch estimates
    ├── orm_fallbacks.py  # SQLite fallback helpers
    └── __init__.py       # public re-exports
```

## Placeholder DSL

Query strings use the `{{name}}` and `{{name::type}}` syntax instead of
the standard `%s` / `%(name)s` placeholders. The transformation happens
in `database._substitute_params` at execution time.

**Why custom syntax?** It auto-documents the expected types right
inside the SQL (``{{websiteId::uuid}}``, ``{{startDate::timestamptz}}``)
without forcing every call site to remember the right cast. Migrating
to standard psycopg placeholders would mean editing ~3000 LOC of SQL
to add ``::uuid`` casts back in by hand.

### Examples

```sql
SELECT * FROM website
WHERE id = {{websiteId::uuid}}
  AND created_at >= {{startDate::timestamptz}}
  AND created_at <  {{endDate::timestamptz}}
```

becomes

```sql
SELECT * FROM website
WHERE id = %s::uuid
  AND created_at >= %s::timestamptz
  AND created_at <  %s::timestamptz
```

with parameters `[website_uuid, start, end]`.

### Supported casts

Any token after `::` is forwarded verbatim to PostgreSQL. The common
casts used in this codebase are:

| Placeholder                | Resolved SQL              | Used for                  |
| -------------------------- | ------------------------- | ------------------------- |
| `{{name}}`                 | `%s`                      | text / numeric values     |
| `{{websiteId::uuid}}`      | `%s::uuid`                | website / user IDs        |
| `{{startDate::timestamptz}}` | `%s::timestamptz`       | datetime bounds           |
| `{{values::text[]}}`       | `%s::text[]`              | array params in `ANY()`   |

## Filter pipeline

`filters.py` exposes a tiny dataclass `Filter(column, operator, value)`
plus three functions used by every query that needs WHERE conditions:

1. `parse_filters_from_params(raw_strings)` — turns CLI/HTTP filter
   parameters into typed `Filter` objects.
2. `prepare_filters(filters)` — returns
   `(filter_where_clause, filter_params_dict, "")`
   ready to splice into a query string.
3. `build_filter_sql(filter)` — single-filter SQL fragment (called by
   `prepare_filters`).

Filters operate only on columns stored directly on `website_event`. There is
no session join in privacy-first aggregate mode.

### Bot filter

`?bot_filter=1` injects a synthetic `Filter(column="__bot_filter__",
operator="eq", value="default")` that `prepare_filters` translates to
the multi-clause exclusion SQL in `build_bot_filter_sql`, applying the
per-website bot-detection config when one exists.

## Public surface

Everything reachable from `apps/analytics/services.py` is documented by
`queries/__init__.py` (the `__all__` list there is authoritative). All
query functions follow the same general signature:

```python
def get_<feature>(
    website_id: str,           # UUID stringified
    start_date: datetime,      # inclusive, UTC
    end_date: datetime,        # exclusive, UTC
    filters: list[Filter] | None = None,
    ...                        # endpoint-specific kwargs
) -> list[dict] | dict
```

Return shapes are declared as `TypedDict` in `types.py` for editor
autocompletion (no runtime cost).

## Adding a new query

1. Pick the right module (`queries/<feature>.py`).
2. Write the SQL using `{{name::type}}` placeholders.
3. Wrap it in a function with the standard signature above.
4. Add the matching `TypedDict` row shape to `types.py`.
5. Re-export from `queries/__init__.py`.
6. Add a smoke test in `tests/test_query_modules_*.py`.

The `raw_query` helper logs and retries transient connection errors
twice with exponential back-off — application code never needs to wrap
queries in try/except blocks for that.
