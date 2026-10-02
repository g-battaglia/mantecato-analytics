# Changelog

All notable changes to Mantecato are documented here.
The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

AI connections publication drafts: [release notes](docs/releases/ai-connections-release-notes.md)
and [GitHub announcement](docs/releases/ai-connections-announcement.md). These are not a published release.

### Added
- **Opt-in AI connections** — Settings → AI connections provides browser consent,
  explicitly selected sites/read scopes, rotating OAuth credentials, show-once
  personal tokens, access reduction/revocation and metadata-only activity.
- **Optional no-expiry personal AI tokens** — explicit “Never expires” choice,
  with a finite 30-day default, live account/site/scope checks, active-grant quotas
  and immediate revocation. OAuth credentials remain time-limited.
- **Visible credential inventory** — opens by default when access exists, with
  personal/OAuth filters, creation/last-use/expiry metadata and direct inline
  revocation, including expired or invalidated entries. Secrets remain show-once.
- **Read-only remote MCP** — eight official-SDK tools reuse existing aggregate
  analytics services on exact `/mcp`; legacy REST keys, CLI and local stdio MCP
  remain separate and compatible.
- **Connection workbench** — one provider guide at a time, keyboard selection,
  light/dark and mobile layouts, a dedicated server-address panel and locally
  served provider marks with pinned provenance and retained licensing.
- **Offline AI cleanup** — bounded credential/audit cleanup and
  `run_daily_maintenance` with independent visitor/AI budgets and outcomes.
- **Remote CLI and MCP clients** — two independent packages now authenticate with
  an API key and use HTTPS. Neither client installs Django or accesses PostgreSQL.
- **Analytics API v1** — additive, strict endpoints for capabilities, schemas,
  totals, dimensional time series, comparisons, dimension discovery and traffic
  quality diagnostics. Existing API and dashboard contracts are unchanged.
- **Content groups** — break traffic down by labels the site declares for each
  page, for sites whose URLs carry no taxonomy of their own (`/p/<slug>`).
  Set them on the tracker tag (`data-groups="guides,pricing"`) and they show up
  under **Sections → Content group**, as a `content_group` filter on every other
  view, and through `GET /api/analytics/groups/`, the independent
  `mantecato top-groups` command and the `groups` breakdown widget. Exact per-group
  unique visitors come from the existing scope-presence mechanism. A page may
  declare several groups (max 12, optionally namespaced as `cat:`/`tag:`), so
  per-group views overlap and do not sum to
  the site total. The labels are page metadata declared by the site owner —
  nothing is read from the visitor — so the consent-free posture is unchanged
  (see `docs/privacy.md`). The Umami-compatible `tag` field, previously sent by
  the tracker and dropped on ingest, now lands as a single group.

### Changed
- Web manifests use native Gunicorn 26 ASGI with bounded connections, keep-alive
  disabled, explicit HTTP/1 close signalling and per-request ORM cleanup. Remote
  AI access remains disabled by default; legacy WSGI hosting remains available
  without remote MCP.
- HTTPS scheme adaptation for MCP is restricted to explicitly trusted proxy
  IPs/CIDRs from `FORWARDED_ALLOW_IPS`; Django proxy configuration is separate.
- Visitor maintenance is offline only: no collector/web-startup rollup or digest
  expiry. An operational daily scheduler is required; analytics formulas,
  monthly deduplication, 396-day digest retention and tracker behavior are unchanged.
- The old database-backed CLI is no longer bundled with the Django server. The
  public Python SDK has been retired in favor of the REST API and separate clients.
- **Relicensed from MIT to the Apache License 2.0.** Apache 2.0 keeps the same
  permissive freedoms but adds an explicit patent grant and trademark clause.
  The full text now lives in the root `LICENSE` file.
- **Fixed, non-configurable visitor-counting privacy posture** (so it cannot be
  misconfigured into needing a consent banner): the dedup window is fixed to one
  **calendar month**, the digest IP is **always truncated** to `/24` (IPv4) /
  `/48` (IPv6) before hashing, and the digest retention is fixed at **396 days**
  (~13 months). The env vars `VISITOR_EXACT_WINDOW`, `VISITOR_HASH_IP_PREFIX_V4`,
  `VISITOR_HASH_IP_PREFIX_V6` and `VISITOR_KEY_RETENTION_DAYS` are removed.
- A returning visitor is now deduplicated within the calendar month; over a
  multi-month range the per-month uniques are summed. The daily rollup finalises a
  month only once it has ended.
- The tracker sends engagement heartbeats via `fetch(keepalive, credentials:"omit")`
  instead of `sendBeacon` (which forces `credentials:"include"`), so no first-party
  cookies are ever sent. URL fragments (`#...`) are discarded like query strings,
  except a token-free hash-based SPA route (`#/...`), which is kept as part of the
  page path so per-route counts survive.
- Docs (`docs/privacy.md`, `docs/accuracy.md`): document the single fixed legal
  posture — no device storage/access (no ePrivacy trigger) + consent-exempt
  audience measurement (first-party, IP masked, ≤13-month identifier, ≤25-month
  retention, transparency + GPC), all satisfied by construction.
- Docs (`docs/accuracy.md` §4): explain why another analytics tool may report
  *more* visitors — ingest-passed search crawlers it keeps counting, and
  rotating-IP headless pools it counts one-visitor-per-IP — both of which
  Mantecato deflates via `navigator.webdriver` refusal, `/24` collapse, and
  datacenter detection, so a lower visitor count is usually more accurate, not
  lost data. Includes the known limitation (spoofed-`webdriver` pools still
  inflate pageviews) and how to reconcile fairly with Umami.

### Fixed
- OAuth redirect validation rejects reserved response parameters even with empty
  values or encoded names, preventing ambiguous callback URLs.
- Concurrent collection avoids native ASGI socket-reuse races and leaked ORM
  connections, verified with isolated local HTTP/resource tests.
- AI cleanup reports `busy` when eligible records were skipped due to row locks,
  preserving committed progress instead of incorrectly reporting completion.
- OAuth revocation remains an idempotent success if cleanup removes the
  connection between credential lookup and row locking.
- OAuth rate-limit keys distinguish clients behind an explicitly configured
  trusted proxy topology without trusting permissive/spoofable forwarding headers.
- Unexpected tool/JSON encoding failures are audited as unavailable, not completed;
  daily-retention documentation consistently names `run_daily_maintenance`.
- HTTP integration tests accept the `DATABASE_URL` fallback and skip unsupported
  database setups before fixture writes or worker startup.
- IPv4-mapped IPv6 client addresses (`::ffff:a.b.c.d`) are now unwrapped to IPv4
  before truncation, so they mask to the `/24` block instead of collapsing every
  such client to `::` (which would have merged them into one visitor).
- **Upgrade safety**: the rollup now decides which windows are finished by their
  real calendar bounds, not by string-comparing the month key. A deployment
  upgrading mid-month from the previous (day-grained) window no longer has the
  open month's still-live, day-keyed state finalised and deleted prematurely —
  which would have corrupted that month's visitor totals. Only salts whose own
  window has ended are discarded, preserving a live legacy day-key's salt.
- Over-retention per-event digests are nulled by bounded offline maintenance,
  independently of month finalization. Timely physical expiry requires the
  operational daily job; ingestion does not perform retention maintenance.
- The "Deduplicated within each month" caveat on the Visitors KPI is shown only
  for ranges that actually span more than one month, not on single-month, today,
  or realtime views.
- The retention sweep (`discard_expired_digests`) uses its dedicated partial
  index (`idx_we_visitor_key_expiry`, on `created_at` where `visitor_key IS NOT
  NULL`) during offline expiry batches; it does not run on collector requests.
- A malformed/unparseable visitor period key (only reachable via DB corruption)
  is now skipped with a warning instead of aborting the whole rollup transaction
  and blocking retention housekeeping.
- The independently scheduled visitor rollup uses set-based, atomic site-period
  units with shared nonblocking advisory locking, resumable progress and finite
  budgets; completed retries do not add counts twice.

### Removed
- The `quarter` and `year` dedup windows (and configurable windows in general);
  the year window had a retention-boundary read bug. The fixed monthly window is
  not affected.

## [4.0.0] — 2026-06-15

Mantecato v4 is a **privacy-first, aggregate-only** release, positioned as
*the ethical, self-hostable web analytics platform*. It measures aggregate
events, not people: cookieless, no browser storage, no fingerprinting, and no
persistent cross-day identifiers — designed to run without an analytics consent
banner in EU/UK/US deployments.

### Added
- Cookieless **exact visitor / visit / bounce** counting via a compute-and-discard
  scheme: a per-window salted `HMAC(salt, website_id|ip|user_agent)` digest used
  only to deduplicate within the window, with the salt discarded at window end
  (forward secrecy — the digest can no longer be linked to a person afterwards).
- **Country-level** geolocation resolved from a local MaxMind database (no third-party call).
- **Global Privacy Control (GPC)** honored by default; Do-Not-Track (DNT) is opt-in.
- Bot detection with a non-destructive, read-time bot filter that cascades to all metrics.
- **Umami-compatible** tracker wire protocol and one-command data import
  (`importumami` / `importumamidata`) to migrate off Umami without re-instrumenting sites.

### Changed
- The raw IP address and User-Agent are **never stored** — used transiently only
  for the salted digest and geolocation, then discarded.
- Query strings are dropped, referrers are reduced to a bare domain, and only the
  coarse browser / os / device class is kept. No custom event payloads beyond the event name.

### Removed
- Sessions, returning-visitor tracking, user journeys, retention cohorts, funnels,
  marketing attribution (UTM / click IDs), session replay, session lists, visitor
  profiles, and revenue. These require stable identifiers and are intentionally unsupported.

### Notes
- License remains **MIT**.
- Mantecato is an independent project and is not affiliated with or endorsed by Umami.

### Known limitations (planned for 4.0.1)
- The operator dashboard currently loads fonts, CSS, JS, and map tiles from public
  CDNs (jsDelivr, Tailwind CDN, unpkg, CARTO). This affects the **operator view only** —
  tracked sites receive nothing but the ~2 KB tracker. Self-hosting these assets and
  replacing the slippy map with a bundled country choropleth is planned for 4.0.1.
