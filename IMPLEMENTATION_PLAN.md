# Mantecato Analytics — Implementation Plan

> A power-analytics dashboard that reads from the same Umami PostgreSQL database.
> Umami collects. Mantecato analyzes.

## 1. Architecture Decision

**Approach**: Standalone Next.js 16 app (NOT a fork of Umami).

**Why not fork**: Umami's UI layer uses `@umami/react-zen`, a proprietary component library with undocumented APIs, opaque TypeScript types, and unpredictable component signatures. Vibe-coding against it is 10x slower than using well-documented libraries. Every component is a surprise (`TextField` passes value directly instead of events, `Card` doesn't exist, `FontColor` accepts only undocumented string literals, `Select` has non-standard signatures). A fork would inherit all this friction and diverge from upstream immediately.

**Why same-DB standalone**: The Umami PostgreSQL schema is clean and well-indexed. We point Prisma at the same database, copy the schema verbatim, and write our own UI with shadcn/ui + Tailwind — libraries every LLM knows perfectly. Umami continues to run in parallel, collecting data via its tracker script. Mantecato is a read-heavy analytics UI with surgical write operations (user preferences, saved views, dashboards).

**Stack**:

| Layer | Technology | Rationale |
|---|---|---|
| Framework | Next.js 16 (App Router) | Same as Umami, SSR + API routes |
| UI Components | shadcn/ui + Radix | Perfectly documented, AI-friendly |
| Styling | Tailwind CSS 4 | Utility-first, fast iteration |
| Charts | Recharts | Already well-known, composable |
| Tables | TanStack Table v8 | Sorting, filtering, pagination, column visibility |
| Drag & Drop | @hello-pangea/dnd | Stable, well-documented |
| State | Zustand | Minimal, no boilerplate |
| Data Fetching | TanStack Query v5 | Caching, deduplication, optimistic updates |
| ORM | Prisma (same schema) | Identical to Umami, shared DB |
| Auth | Shared with Umami | Same `user` table, bcrypt verification |
| Date handling | date-fns | Lightweight, tree-shakeable |
| Export | xlsx (CSV/Excel), jspdf + html2canvas (PDF) | Real export, not canvas hacks |
| Icons | Lucide React | Standard, complete set |

---

## 2. Umami Database Schema (read-only reference)

Mantecato connects to the **same PostgreSQL database** as Umami. The Prisma schema is copied 1:1. Mantecato **never runs migrations** — Umami owns the schema.

### Tables we READ (analytics):

| Table | Purpose | Key Fields |
|---|---|---|
| `website_event` | Every pageview + custom event | `website_id`, `session_id`, `visit_id`, `created_at`, `url_path`, `url_query`, `referrer_domain`, `referrer_path`, `page_title`, `event_type` (1=pageview, 2=custom), `event_name`, `tag`, `hostname`, UTM fields (`utm_source/medium/campaign/content/term`), click IDs (`gclid/fbclid/msclkid/ttclid/twclid/li_fat_id`) |
| `session` | Visitor sessions | `session_id`, `website_id`, `browser`, `os`, `device`, `screen`, `language`, `country`, `region`, `city`, `distinct_id`, `created_at` |
| `event_data` | Key-value data attached to events | `website_id`, `website_event_id`, `data_key`, `string_value`, `number_value`, `date_value`, `data_type` (1=string, 2=number, 4=date) |
| `session_data` | Key-value data attached to sessions | `website_id`, `session_id`, `data_key`, `string_value`, `number_value`, `date_value`, `data_type`, `distinct_id` |
| `revenue` | Monetary events | `website_id`, `session_id`, `event_id`, `event_name`, `revenue`, `currency` |
| `website` | Site configuration | `website_id`, `name`, `domain`, `share_id`, `user_id`, `team_id` |

### Tables we READ + WRITE (config):

| Table | Purpose | Our Usage |
|---|---|---|
| `user` | User accounts | READ for auth (verify bcrypt password) |
| `team` / `team_user` | Teams | READ for permissions |
| `report` | Saved configurations (JSON `parameters`) | WRITE: saved views, dashboards, annotations, alerts (using `type` field to namespace) |
| `segment` | Audience segments | READ existing Umami segments |

### Tables we DON'T touch:

| Table | Reason |
|---|---|
| `link` | URL shortener feature, irrelevant |
| `pixel` | Tracking pixel feature, irrelevant |

### Important indexes on `website_event` (for query planning):

- `(website_id, created_at)` — the primary analytics index
- `(website_id, created_at, url_path)` — page-level queries
- `(website_id, created_at, event_name)` — event queries
- `(website_id, created_at, referrer_domain)` — referrer queries
- `(website_id, created_at, page_title)` — title queries
- `(website_id, created_at, tag)` — tag queries
- `(website_id, created_at, hostname)` — multi-domain queries
- `(website_id, session_id, created_at)` — session-scoped queries
- `(website_id, visit_id, created_at)` — visit-scoped queries

---

## 3. Auth System

Shared authentication with Umami. Same `user` table, same bcrypt passwords.

### Login flow:

1. User enters username + password on Mantecato login page
2. Query `SELECT * FROM user WHERE username = $1 AND deleted_at IS NULL`
3. Verify password with `bcrypt.compare(input, user.password)`
4. Issue a JWT (or use `iron-session` for encrypted cookies)
5. Store `{ userId, username, role }` in session

### Authorization:

- `role = 'admin'` — full access to all websites
- Regular users — access websites where `website.user_id = userId` OR where user is a team member (`team_user.user_id = userId` AND `website.team_id = team_user.team_id`)
- Share tokens — public dashboards via `website.share_id`

### Implementation:

```
src/lib/auth.ts          — verifyPassword, createSession, getSession
src/middleware.ts         — protect routes, redirect to /login if no session
src/app/login/page.tsx    — login form
```

---

## 4. Project Structure

```
mantecato/
├── prisma/
│   └── schema.prisma              # Copied from Umami, NO migrations
├── src/
│   ├── app/
│   │   ├── layout.tsx              # Root layout with providers
│   │   ├── login/
│   │   │   └── page.tsx            # Login page
│   │   ├── (dashboard)/
│   │   │   ├── layout.tsx          # Authenticated layout (sidebar + header)
│   │   │   ├── page.tsx            # Home — website selector
│   │   │   ├── sites/
│   │   │   │   └── [siteId]/
│   │   │   │       ├── layout.tsx  # Site-scoped layout (nav tabs)
│   │   │   │       ├── page.tsx    # Overview dashboard
│   │   │   │       ├── pages/
│   │   │   │       │   └── page.tsx        # Page-level analytics
│   │   │   │       ├── events/
│   │   │   │       │   └── page.tsx        # Event analytics
│   │   │   │       ├── sessions/
│   │   │   │       │   └── page.tsx        # Session explorer
│   │   │   │       ├── sources/
│   │   │   │       │   └── page.tsx        # Traffic sources & UTM
│   │   │   │       ├── geo/
│   │   │   │       │   └── page.tsx        # Geographic analysis
│   │   │   │       ├── devices/
│   │   │   │       │   └── page.tsx        # Devices, browsers, OS
│   │   │   │       ├── retention/
│   │   │   │       │   └── page.tsx        # Cohort retention
│   │   │   │       ├── funnels/
│   │   │   │       │   └── page.tsx        # Funnel analysis
│   │   │   │       ├── journeys/
│   │   │   │       │   └── page.tsx        # User journey flows
│   │   │   │       ├── compare/
│   │   │   │       │   └── page.tsx        # Period comparison
│   │   │   │       ├── realtime/
│   │   │   │       │   └── page.tsx        # Live visitors
│   │   │   │       └── revenue/
│   │   │   │           └── page.tsx        # Revenue analytics
│   │   │   ├── dashboards/
│   │   │   │   ├── page.tsx                # Custom dashboards list
│   │   │   │   └── [dashboardId]/
│   │   │   │       └── page.tsx            # Custom dashboard view
│   │   │   └── settings/
│   │   │       └── page.tsx                # User preferences
│   │   └── api/
│   │       ├── auth/
│   │       │   └── route.ts                # Login/logout
│   │       └── sites/
│   │           └── [siteId]/
│   │               ├── stats/route.ts      # Overview stats
│   │               ├── pageviews/route.ts   # Pageview time series
│   │               ├── pages/route.ts       # Top pages
│   │               ├── events/route.ts      # Event analytics
│   │               ├── sessions/route.ts    # Session data
│   │               ├── sources/route.ts     # Referrers + UTM
│   │               ├── geo/route.ts         # Geographic data
│   │               ├── devices/route.ts     # Device/browser/OS
│   │               ├── retention/route.ts   # Cohort retention
│   │               ├── funnels/route.ts     # Funnel analysis
│   │               ├── journeys/route.ts    # User journeys
│   │               ├── compare/route.ts     # Period comparison
│   │               ├── realtime/route.ts    # Active visitors
│   │               ├── revenue/route.ts     # Revenue data
│   │               ├── time-on-page/route.ts # Per-page duration
│   │               └── slugs/route.ts       # Slug-level analysis
│   ├── components/
│   │   ├── ui/                     # shadcn/ui components (auto-generated)
│   │   ├── charts/                 # Recharts wrappers
│   │   │   ├── AreaChart.tsx
│   │   │   ├── BarChart.tsx
│   │   │   ├── LineChart.tsx
│   │   │   ├── PieChart.tsx
│   │   │   ├── FunnelChart.tsx
│   │   │   ├── RetentionGrid.tsx
│   │   │   ├── WorldMap.tsx
│   │   │   └── Sparkline.tsx
│   │   ├── data/                   # Data display components
│   │   │   ├── DataTable.tsx       # TanStack Table wrapper
│   │   │   ├── MetricCard.tsx
│   │   │   ├── ComparisonBadge.tsx
│   │   │   └── TrendIndicator.tsx
│   │   ├── filters/                # Filter UI
│   │   │   ├── DateRangePicker.tsx
│   │   │   ├── DatePresets.tsx
│   │   │   ├── FilterBar.tsx
│   │   │   ├── CompareToggle.tsx
│   │   │   └── GranularitySelector.tsx
│   │   ├── layout/                 # Layout components
│   │   │   ├── Sidebar.tsx
│   │   │   ├── Header.tsx
│   │   │   ├── SiteSelector.tsx
│   │   │   └── SiteNav.tsx
│   │   ├── dashboard/              # Custom dashboard components
│   │   │   ├── DashboardGrid.tsx
│   │   │   ├── WidgetWrapper.tsx
│   │   │   └── AddWidgetDialog.tsx
│   │   └── export/                 # Export components
│   │       ├── ExportMenu.tsx
│   │       └── ExportDialog.tsx
│   ├── lib/
│   │   ├── prisma.ts               # Prisma client singleton
│   │   ├── auth.ts                 # Auth utilities
│   │   ├── queries.ts              # Raw SQL query builder (from Umami patterns)
│   │   ├── date.ts                 # Date utilities
│   │   ├── format.ts               # Number/currency formatting
│   │   ├── export.ts               # CSV/JSON/PDF export logic
│   │   └── constants.ts            # App constants
│   ├── queries/                    # SQL query functions
│   │   ├── stats.ts                # Website stats (pageviews, visitors, bounces, time)
│   │   ├── pageviews.ts            # Pageview time series + top pages
│   │   ├── sessions.ts             # Session metrics + explorer
│   │   ├── events.ts               # Event analytics
│   │   ├── sources.ts              # Referrers, UTM, channels
│   │   ├── geo.ts                  # Country/region/city
│   │   ├── devices.ts              # Browser/OS/device/screen
│   │   ├── retention.ts            # Cohort retention (CTE)
│   │   ├── funnels.ts              # Funnel analysis (dynamic CTEs)
│   │   ├── journeys.ts             # User journey paths
│   │   ├── revenue.ts              # Revenue analytics
│   │   ├── time-on-page.ts         # Per-page duration analysis
│   │   ├── compare.ts              # Period comparison queries
│   │   ├── realtime.ts             # Active visitors
│   │   └── slugs.ts                # URL slug aggregation
│   ├── hooks/                      # React hooks
│   │   ├── use-query.ts            # TanStack Query wrappers
│   │   ├── use-date-range.ts       # Date range state
│   │   ├── use-filters.ts          # Filter state
│   │   ├── use-preferences.ts      # User preferences (localStorage)
│   │   └── use-site.ts             # Current site context
│   └── stores/                     # Zustand stores
│       ├── filters.ts              # Global filter state
│       └── preferences.ts          # User preferences
├── public/
├── tailwind.config.ts
├── next.config.ts
├── package.json
└── tsconfig.json
```

---

## 5. Core Analytics Pages — Detailed Spec

### 5.1 Overview Dashboard (`/sites/[siteId]`)

The main dashboard. Shows key metrics at a glance with time series.

**Metrics bar** (configurable, drag-to-reorder):
- Pageviews (total count, % change vs previous period)
- Unique Visitors (distinct session_id)
- Visits (distinct visit_id)
- Bounce Rate (single-page visits / total visits * 100)
- Avg Visit Duration (total_time / visits)
- Pages per Visit (pageviews / visits)

**SQL for metrics bar** (adapted from Umami's `getWebsiteStats`):

```sql
SELECT
  COALESCE(SUM(t.c), 0)::bigint AS pageviews,
  COUNT(DISTINCT t.session_id) AS visitors,
  COUNT(DISTINCT t.visit_id) AS visits,
  COALESCE(SUM(CASE WHEN t.c = 1 THEN 1 ELSE 0 END), 0) AS bounces,
  COALESCE(SUM(FLOOR(EXTRACT(EPOCH FROM (t.max_time - t.min_time)))), 0)::bigint AS totaltime
FROM (
  SELECT
    session_id, visit_id,
    COUNT(*) AS c,
    MIN(created_at) AS min_time,
    MAX(created_at) AS max_time
  FROM website_event
  WHERE website_id = $1::uuid
    AND created_at BETWEEN $2 AND $3
    AND event_type = 1
  GROUP BY 1, 2
) AS t
```

**Charts**:
- Primary: Area chart of pageviews over time (granularity: hour/day/week/month auto-selected by range)
- Secondary: Overlaid line of unique visitors
- Optional: Comparison overlay (previous period, dotted line)

**Panels** (configurable visibility + order):
- Top Pages (url_path, ranked by views)
- Top Referrers (referrer_domain, ranked by visitors)
- Browsers (pie chart)
- Operating Systems (pie chart)
- Devices (pie chart — desktop/mobile/tablet)
- Countries (world map + table)
- Top Events (event_name, ranked by count)

### 5.2 Page Analytics (`/sites/[siteId]/pages`)

Deep dive into individual pages. The killer feature Umami lacks.

**Page list view**:
- Table with columns: URL Path, Page Title, Views, Unique Visitors, Avg Time on Page, Bounce Rate, Entry %, Exit %
- Sortable by any column
- Filterable by path pattern (e.g., `/blog/*`)
- Group by slug (strip query params + trailing slash) or by full path

**SQL for time on page** (this is a new query Umami doesn't have):

```sql
-- Time on page: for each pageview, calculate time until next pageview in the same visit
WITH page_sequence AS (
  SELECT
    url_path,
    visit_id,
    created_at,
    LEAD(created_at) OVER (PARTITION BY visit_id ORDER BY created_at) AS next_page_at
  FROM website_event
  WHERE website_id = $1::uuid
    AND created_at BETWEEN $2 AND $3
    AND event_type = 1
)
SELECT
  url_path,
  COUNT(*) AS views,
  COUNT(DISTINCT visit_id) AS visitors,
  AVG(EXTRACT(EPOCH FROM (next_page_at - created_at)))
    FILTER (WHERE next_page_at IS NOT NULL) AS avg_time_on_page,
  PERCENTILE_CONT(0.5) WITHIN GROUP (
    ORDER BY EXTRACT(EPOCH FROM (next_page_at - created_at))
  ) FILTER (WHERE next_page_at IS NOT NULL) AS median_time_on_page
FROM page_sequence
GROUP BY url_path
ORDER BY views DESC
```

**SQL for entry/exit pages**:

```sql
-- Entry pages: first page of each visit
WITH visit_pages AS (
  SELECT
    visit_id,
    url_path,
    ROW_NUMBER() OVER (PARTITION BY visit_id ORDER BY created_at ASC) AS rn_entry,
    ROW_NUMBER() OVER (PARTITION BY visit_id ORDER BY created_at DESC) AS rn_exit
  FROM website_event
  WHERE website_id = $1::uuid
    AND created_at BETWEEN $2 AND $3
    AND event_type = 1
)
SELECT
  url_path,
  COUNT(*) FILTER (WHERE rn_entry = 1) AS entries,
  COUNT(*) FILTER (WHERE rn_exit = 1) AS exits
FROM visit_pages
WHERE rn_entry = 1 OR rn_exit = 1
GROUP BY url_path
```

**Single page view** (click into a page):
- Time series of views for that specific url_path
- Time on page distribution (histogram)
- Where visitors come from (referrer breakdown for this page)
- Where visitors go next (next page breakdown)
- Scroll depth (if tracked via event_data with `$scroll-depth` events)

### 5.3 Event Analytics (`/sites/[siteId]/events`)

**Event list**:
- Table: Event Name, Total Count, Unique Visitors, Last Triggered
- Click into event for detail view

**Event detail view**:
- Time series of event occurrences
- Event properties breakdown (from `event_data` key-value pairs)
- Property values distribution per key
- Visitors who triggered this event

**SQL for event properties**:

```sql
SELECT
  ed.data_key,
  COALESCE(ed.string_value, ed.number_value::text) AS value,
  COUNT(*) AS count,
  COUNT(DISTINCT we.session_id) AS visitors
FROM event_data ed
JOIN website_event we ON ed.website_event_id = we.event_id
WHERE ed.website_id = $1::uuid
  AND ed.created_at BETWEEN $2 AND $3
  AND we.event_name = $4
GROUP BY 1, 2
ORDER BY count DESC
```

### 5.4 Session Explorer (`/sites/[siteId]/sessions`)

Browse individual user sessions. A feature Umami doesn't expose well.

**Session list**:
- Table: Session ID (truncated), Country/City, Browser, OS, Device, Pages Viewed, Duration, Started At
- Filter by country, browser, OS, device
- Filter by specific page visited
- Filter by specific event triggered

**Session detail view** (click into session):
- Timeline of all events in the session, chronologically
- Each event shows: timestamp, url_path, page_title, event_name (if custom), event_data properties
- Visual session replay in terms of page flow (not actual screen recording — just the sequence of pages with time gaps)

**SQL for session activity**:

```sql
SELECT
  we.created_at,
  we.url_path,
  we.page_title,
  we.event_type,
  we.event_name,
  we.referrer_domain,
  we.visit_id,
  json_agg(
    json_build_object('key', ed.data_key, 'value', COALESCE(ed.string_value, ed.number_value::text))
  ) FILTER (WHERE ed.data_key IS NOT NULL) AS event_data
FROM website_event we
LEFT JOIN event_data ed ON we.event_id = ed.website_event_id
WHERE we.session_id = $1::uuid
  AND we.website_id = $2::uuid
GROUP BY we.event_id, we.created_at, we.url_path, we.page_title,
         we.event_type, we.event_name, we.referrer_domain, we.visit_id
ORDER BY we.created_at ASC
```

### 5.5 Traffic Sources (`/sites/[siteId]/sources`)

**Views**:
1. **Referrers** — `referrer_domain` ranked by visitors
2. **UTM Campaigns** — grouped by `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term`
3. **Channels** — auto-classified (Direct, Organic Search, Social, Referral, Email, Paid) based on referrer_domain + UTM
4. **Click IDs** — `gclid`, `fbclid`, `msclkid` etc. presence/counts (paid traffic identification)

Each view has:
- Table with metrics (visitors, pageviews, bounce rate, avg duration)
- Drill-down capability (click a source to see pages visited from that source)

### 5.6 Geographic Analysis (`/sites/[siteId]/geo`)

**Views**:
1. **World map** — choropleth colored by visitor count per country
2. **Country table** — Country, Visitors, Pageviews, Bounce Rate, Avg Duration
3. **Region drill-down** — click a country to see regions
4. **City drill-down** — click a region to see cities

**SQL for geo with metrics**:

```sql
SELECT
  s.country,
  s.region,
  s.city,
  COUNT(DISTINCT we.session_id) AS visitors,
  COUNT(*) AS pageviews,
  COUNT(DISTINCT we.visit_id) AS visits
FROM website_event we
JOIN session s ON we.session_id = s.session_id
WHERE we.website_id = $1::uuid
  AND we.created_at BETWEEN $2 AND $3
  AND we.event_type = 1
GROUP BY 1, 2, 3
ORDER BY visitors DESC
```

### 5.7 Device Analytics (`/sites/[siteId]/devices`)

**Breakdown by**: Browser, OS, Device type, Screen resolution, Language
Each with pie/bar chart + table with visitor/pageview counts.

### 5.8 Cohort Retention (`/sites/[siteId]/retention`)

Reuse Umami's existing CTE-based retention query. Display as a triangular grid:
- Rows: cohort weeks/months (when users first visited)
- Columns: periods since first visit (Week 0, Week 1, ..., Week N)
- Cells: % of cohort that returned
- Color-coded (darker = higher retention)

### 5.9 Funnel Analysis (`/sites/[siteId]/funnels`)

Reuse Umami's dynamic CTE funnel query. UI:
- Define steps: each step is a URL path or event name
- Set time window between steps
- Visual funnel chart showing drop-off at each step
- Conversion rate between consecutive steps
- Overall conversion rate

### 5.10 User Journeys (`/sites/[siteId]/journeys`)

Reuse Umami's journey query. Show as:
- Sankey diagram of page-to-page flows
- Top N paths (sequences of 3-5 pages)
- Entry points and exit points highlighted

### 5.11 Period Comparison (`/sites/[siteId]/compare`)

The **flagship feature** for temporal analysis.

**Capabilities**:
- Compare any two date ranges side by side
- Quick presets: This week vs last week, This month vs last month, This quarter vs last quarter, This year vs last year
- Custom: pick any two arbitrary ranges
- All metrics shown with absolute values + % change
- Overlaid time series (current solid, comparison dashed)
- Breakdown tables with delta columns

**SQL pattern** (two queries unioned or run in parallel):

```sql
-- Current period
SELECT 'current' AS period, ... FROM website_event WHERE created_at BETWEEN $2 AND $3 ...
UNION ALL
-- Comparison period
SELECT 'previous' AS period, ... FROM website_event WHERE created_at BETWEEN $4 AND $5 ...
```

### 5.12 Revenue Analytics (`/sites/[siteId]/revenue`)

From the `revenue` table:
- Total revenue over time
- Revenue by event (which actions generate money)
- Revenue by source (which referrers drive revenue)
- Revenue by country
- ARPU (average revenue per user)
- Revenue trends with period comparison

### 5.13 Realtime (`/sites/[siteId]/realtime`)

- Current active visitors (sessions with events in last 5 minutes)
- Live event stream (polling every 5 seconds)
- Currently viewed pages
- Current visitor map

---

## 6. Slug-Based vs Path-Based Analysis

A key differentiator. Umami only shows raw `url_path`. Mantecato offers both views:

### Path mode (default):
- `/blog/my-post` and `/blog/my-post?utm_source=twitter` are different rows
- Full `url_path` + `url_query` shown

### Slug mode:
- Strips query parameters
- Normalizes trailing slashes (`/blog/` = `/blog`)
- Groups by pattern (e.g., all `/blog/*` pages together)
- Option to define custom slug patterns via regex

**SQL for slug grouping**:

```sql
SELECT
  REGEXP_REPLACE(url_path, '/+$', '') AS slug,
  COUNT(*) AS views,
  COUNT(DISTINCT session_id) AS visitors,
  COUNT(DISTINCT visit_id) AS visits
FROM website_event
WHERE website_id = $1::uuid
  AND created_at BETWEEN $2 AND $3
  AND event_type = 1
GROUP BY 1
ORDER BY views DESC
```

### Hostname-based analysis:
Since `hostname` is on `website_event`, we can break down metrics per subdomain/domain when a single Umami website tracks multiple hostnames:

```sql
SELECT
  hostname,
  COUNT(*) AS pageviews,
  COUNT(DISTINCT session_id) AS visitors
FROM website_event
WHERE website_id = $1::uuid
  AND created_at BETWEEN $2 AND $3
  AND event_type = 1
GROUP BY 1
ORDER BY pageviews DESC
```

---

## 7. Date Range System

### Presets:

| Preset | Range |
|---|---|
| Today | Start of today → now |
| Yesterday | Start of yesterday → end of yesterday |
| Last 24 hours | now - 24h → now |
| Last 7 days | now - 7d → now |
| Last 14 days | now - 14d → now |
| Last 30 days | now - 30d → now |
| Last 60 days | now - 60d → now |
| Last 90 days | now - 90d → now |
| Last 6 months | now - 6mo → now |
| Last 12 months | now - 12mo → now |
| This week | Monday → now |
| Last week | Previous Monday → previous Sunday |
| This month | 1st of month → now |
| Last month | 1st of prev month → last day of prev month |
| This quarter | Q start → now |
| Last quarter | Previous Q start → previous Q end |
| This year | Jan 1 → now |
| Last year | Previous Jan 1 → previous Dec 31 |
| All time | First event → now |
| Custom range | Calendar picker |

### Auto-granularity:

| Range span | Default granularity |
|---|---|
| ≤ 1 day | Hourly |
| 2-14 days | Daily |
| 15-90 days | Daily (weekly optional) |
| 91-365 days | Weekly |
| > 365 days | Monthly |

User can override granularity manually.

### Comparison modes:

| Mode | Behavior |
|---|---|
| Previous period | Same duration, immediately before |
| Previous year | Same dates, previous year |
| Custom | Any arbitrary range |
| None | No comparison |

---

## 8. Filter System

Global filters that apply across all views on a site. Persisted in URL search params for shareability.

### Available filters:

| Filter | Source | UI |
|---|---|---|
| URL Path | `website_event.url_path` | Text input with autocomplete |
| URL contains | `website_event.url_path LIKE` | Text input |
| Page Title | `website_event.page_title` | Text input with autocomplete |
| Hostname | `website_event.hostname` | Dropdown |
| Referrer Domain | `website_event.referrer_domain` | Text input with autocomplete |
| UTM Source | `website_event.utm_source` | Dropdown |
| UTM Medium | `website_event.utm_medium` | Dropdown |
| UTM Campaign | `website_event.utm_campaign` | Dropdown |
| Browser | `session.browser` | Dropdown |
| OS | `session.os` | Dropdown |
| Device | `session.device` | Dropdown |
| Country | `session.country` | Dropdown with search |
| Region | `session.region` | Dropdown with search |
| City | `session.city` | Dropdown with search |
| Language | `session.language` | Dropdown |
| Screen | `session.screen` | Dropdown |
| Event Name | `website_event.event_name` | Dropdown |
| Tag | `website_event.tag` | Text input |

### Filter logic:
- Multiple filters are AND-ed
- Same filter type with multiple values is OR-ed
- Negative filters (exclude) supported with `NOT` prefix

### SQL filter generation:

Following Umami's `parseFilters` pattern, build dynamic WHERE clauses:

```typescript
function buildFilterSQL(filters: Filter[]): { sql: string; params: Record<string, any> } {
  const clauses: string[] = [];
  const params: Record<string, any> = {};
  let needsSessionJoin = false;

  for (const filter of filters) {
    if (SESSION_COLUMNS.includes(filter.column)) {
      needsSessionJoin = true;
      clauses.push(`s.${filter.column} = {{${filter.column}}}`);
    } else {
      clauses.push(`we.${filter.column} = {{${filter.column}}}`);
    }
    params[filter.column] = filter.value;
  }

  return {
    sql: clauses.length > 0 ? `AND ${clauses.join(' AND ')}` : '',
    params,
    needsSessionJoin,
  };
}
```

---

## 9. Custom Dashboards

Users can create custom dashboards with drag-and-drop widgets. Stored in the `report` table with `type = 'mantecato-dashboard'`.

### Widget types:

| Type | Description |
|---|---|
| `metric` | Single number with trend (e.g., "Pageviews: 12,345 +5.2%") |
| `time-series` | Line/area/bar chart over time |
| `table` | Data table with configurable columns |
| `pie` | Pie/donut chart |
| `map` | World map choropleth |
| `funnel` | Funnel visualization |
| `retention` | Retention grid |
| `note` | Markdown text note |
| `comparison` | Side-by-side period comparison for a metric |

### Dashboard config (stored as JSON in `report.parameters`):

```json
{
  "version": 1,
  "layout": "grid",
  "columns": 12,
  "widgets": [
    {
      "id": "w1",
      "type": "metric",
      "title": "Pageviews",
      "x": 0, "y": 0, "w": 3, "h": 1,
      "config": {
        "metric": "pageviews",
        "comparison": "previous_period"
      }
    },
    {
      "id": "w2",
      "type": "time-series",
      "title": "Traffic Over Time",
      "x": 0, "y": 1, "w": 8, "h": 3,
      "config": {
        "metrics": ["pageviews", "visitors"],
        "chartType": "area",
        "granularity": "auto"
      }
    }
  ],
  "filters": {},
  "dateRange": "30day"
}
```

---

## 10. Export System

### Export formats:

| Format | Library | Notes |
|---|---|---|
| CSV | Native | Streaming for large datasets |
| JSON | Native | Structured export |
| Excel (.xlsx) | `xlsx` | Multi-sheet workbooks (one sheet per table) |
| PDF | `jspdf` + `html2canvas` | Visual report with charts as images |
| PNG | `html2canvas` | Screenshot of any chart/table |

### Export scoping:
- Export current view (whatever table/chart is visible)
- Export entire page (all tables on current page)
- Export dashboard (all widgets)
- Scheduled exports (future — store config in `report` table)

---

## 11. User Preferences (localStorage)

All preferences stored in `localStorage` under `mantecato.*` keys.

| Key | Type | Default | Description |
|---|---|---|---|
| `mantecato.theme` | `'light' \| 'dark' \| 'system'` | `'system'` | Color theme |
| `mantecato.dateRange` | `string` | `'30day'` | Default date range preset |
| `mantecato.granularity` | `string` | `'auto'` | Default time granularity |
| `mantecato.comparison` | `string` | `'previous_period'` | Default comparison mode |
| `mantecato.tableRows` | `number` | `10` | Default rows per table |
| `mantecato.chartType` | `string` | `'area'` | Default chart type |
| `mantecato.numberFormat` | `string` | `'compact'` | Number formatting |
| `mantecato.currency` | `string` | `'USD'` | Currency for revenue |
| `mantecato.timezone` | `string` | `Intl default` | Timezone for date display |
| `mantecato.pageMode` | `'path' \| 'slug'` | `'slug'` | Page grouping mode |
| `mantecato.metricsBar` | `string[]` | All 6 metrics | Which metrics to show + order |
| `mantecato.sidebarCollapsed` | `boolean` | `false` | Sidebar state |

---

## 12. Query Engine (`src/lib/queries.ts`)

A clean query builder adapted from Umami's `prisma.rawQuery` pattern but simplified (PostgreSQL only, no ClickHouse branching).

```typescript
import { PrismaClient } from '@/generated/prisma';

const prisma = new PrismaClient();

type QueryParams = Record<string, any>;

/**
 * Execute raw SQL with named parameter substitution.
 * Parameters use {{name}} or {{name::type}} syntax.
 *
 * Example:
 *   rawQuery('SELECT * FROM website_event WHERE website_id = {{websiteId::uuid}}', { websiteId: '...' })
 *   becomes: SELECT * FROM website_event WHERE website_id = $1::uuid
 */
export async function rawQuery<T = any>(sql: string, data: QueryParams = {}): Promise<T[]> {
  const params: any[] = [];

  const query = sql.replaceAll(/\{\{\s*(\w+)(::[\w\[\]]+)?\s*\}\}/g, (_, name, type) => {
    params.push(data[name]);
    return `$${params.length}${type ?? ''}`;
  });

  return prisma.$queryRawUnsafe<T[]>(query, ...params);
}

/**
 * Execute a paged raw query. Returns { data, count, page, pageSize }.
 */
export async function pagedRawQuery<T = any>(
  sql: string,
  data: QueryParams,
  page = 1,
  pageSize = 50,
): Promise<{ data: T[]; count: number; page: number; pageSize: number }> {
  const countSql = `SELECT COUNT(*) AS count FROM (${sql}) AS t`;
  const [{ count }] = await rawQuery<{ count: bigint }>(countSql, data);

  const pagedSql = `${sql} LIMIT ${pageSize} OFFSET ${(page - 1) * pageSize}`;
  const rows = await rawQuery<T>(pagedSql, data);

  return { data: rows, count: Number(count), page, pageSize };
}
```

---

## 13. Implementation Phases

### Phase 1: Foundation (Day 1)

1. Initialize Next.js 16 project with TypeScript, Tailwind, shadcn/ui
2. Copy Prisma schema from Umami (no migrations, `db pull` only)
3. Implement auth (login page, session management, middleware)
4. Create layout (sidebar, header, site selector)
5. Implement query engine (`rawQuery`, `pagedRawQuery`)
6. Implement date range system (presets, custom range, URL persistence)
7. Implement filter system (filter bar, URL persistence)

### Phase 2: Core Analytics (Day 2)

1. Overview dashboard (metrics bar + time series + panels)
2. Page analytics (table + time on page + entry/exit)
3. Source analytics (referrers + UTM + channels)
4. Device analytics (browser + OS + device)
5. Geographic analysis (map + country/region/city tables)

### Phase 3: Advanced Analytics (Day 3)

1. Event analytics (event list + properties + time series)
2. Session explorer (session list + detail view + activity timeline)
3. Period comparison (dual range picker + overlaid charts + delta tables)
4. Slug-based analysis + hostname breakdown
5. Realtime page (active visitors + live stream)

### Phase 4: Reports & Features (Day 4)

1. Cohort retention (grid visualization)
2. Funnel analysis (step builder + visualization)
3. User journeys (Sankey diagram)
4. Revenue analytics (revenue over time + by source)
5. Export system (CSV, JSON, Excel, PDF, PNG)

### Phase 5: Customization (Day 5)

1. Custom dashboards (create, edit, drag-drop widgets)
2. Dashboard widget library (all widget types)
3. User preferences page
4. Dark mode / theme system
5. Saved views (save current filters + date range as a named view)

---

## 14. Key SQL Queries to Port from Umami

These queries from Umami's `src/queries/sql/` should be adapted:

| Umami File | Mantecato Query | Changes |
|---|---|---|
| `getWebsiteStats.ts` | `stats.ts` | Remove ClickHouse branch, add pages-per-visit |
| `pageviews/getPageviewStats.ts` | `pageviews.ts` | Add slug mode, hostname grouping |
| `pageviews/getPageviewMetrics.ts` | `pageviews.ts` | Add time-on-page, entry/exit calculation |
| `sessions/getSessionMetrics.ts` | `sessions.ts` | Keep as-is (browser/OS/device/country breakdown) |
| `sessions/getSessionActivity.ts` | `sessions.ts` | Add event_data join |
| `events/getEventMetrics.ts` | `events.ts` | Add property breakdown |
| `events/getEventData.ts` | `events.ts` | Keep as-is |
| `reports/getRetention.ts` | `retention.ts` | Keep CTE logic, simplify output |
| `reports/getFunnel.ts` | `funnels.ts` | Keep dynamic CTE chain |
| `reports/getJourney.ts` | `journeys.ts` | Keep as-is |
| `reports/getRevenue.ts` | `revenue.ts` | Add by-source, by-country breakdown |
| `reports/getBreakdown.ts` | `stats.ts` | Multi-dimensional breakdown utility |
| `getActiveVisitors.ts` | `realtime.ts` | Keep as-is |
| `getRealtimeData.ts` | `realtime.ts` | Keep as-is |
| **NEW** | `time-on-page.ts` | Page sequence analysis with LEAD() window function |
| **NEW** | `compare.ts` | Dual-period query with UNION ALL or parallel execution |
| **NEW** | `slugs.ts` | URL normalization + regex grouping |

---

## 15. Visual Design Guidelines

- **Clean, dense, information-rich** — more Plausible/PostHog than Google Analytics
- **Dark mode first** — analytics dashboards are used for extended periods
- **Monochrome with accent** — gray scale for structure, single accent color for interactive elements and positive trends
- **Red for negative trends, green for positive** — standard convention
- **Dense tables** — small row height, many rows visible, sticky headers
- **Subtle chart grid lines** — don't compete with data
- **Responsive but desktop-first** — analytics is primarily a desktop activity
- **Consistent spacing** — 4px grid system via Tailwind
- **Chart colors** — a carefully chosen 8-color palette that works in both light and dark mode, distinguishable by colorblind users

---

## 16. Performance Considerations

- **Query-level caching**: TanStack Query with `staleTime: 60_000` (1 minute) for most queries, `staleTime: 5_000` for realtime
- **API response caching**: Next.js route handler caching with `revalidate` for popular date ranges
- **Large date ranges**: For "All time" or ranges > 1 year, auto-aggregate to monthly granularity
- **Table virtualization**: TanStack Virtual for tables with 1000+ rows
- **Chart downsampling**: Limit time series to ~500 data points max, downsample if needed
- **Lazy loading**: Each panel/widget fetches independently, with skeleton loading states
- **URL state**: Filters and date range stored in URL params for fast navigation and shareability

---

## 17. Non-Goals (explicitly out of scope)

- **No tracker modification**: Umami's tracker handles data collection. We don't touch it.
- **No database migrations**: We never ALTER the Umami schema. Read existing tables only.
- **No user management UI**: Users are managed through Umami's admin interface.
- **No ClickHouse support (initially)**: PostgreSQL only. ClickHouse can be added later.
- **No event ingestion**: We don't receive or store events. We only read what Umami collected.
- **No real-time websockets**: Polling-based realtime (every 5 seconds). WebSocket upgrade is a future optimization.
