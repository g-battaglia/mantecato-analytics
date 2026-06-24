# Changelog

All notable changes to Mantecato are documented here.
The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Changed
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
  cookies are ever sent. URL fragments (`#...`) are discarded like query strings.
- Docs (`docs/privacy.md`, `docs/accuracy.md`): document the single fixed legal
  posture — no device storage/access (no ePrivacy trigger) + consent-exempt
  audience measurement (first-party, IP masked, ≤13-month identifier, ≤25-month
  retention, transparency + GPC), all satisfied by construction.

### Fixed
- IPv4-mapped IPv6 client addresses (`::ffff:a.b.c.d`) are now unwrapped to IPv4
  before truncation, so they mask to the `/24` block instead of collapsing every
  such client to `::` (which would have merged them into one visitor).
- **Upgrade safety**: the rollup now decides which windows are finished by their
  real calendar bounds, not by string-comparing the month key. A deployment
  upgrading mid-month from the previous (day-grained) window no longer has the
  open month's still-live, day-keyed state finalised and deleted prematurely —
  which would have corrupted that month's visitor totals. Only salts whose own
  window has ended are discarded, preserving a live legacy day-key's salt.
- Over-retention per-event digests are now nulled on the write-path's throttled
  cadence (and by the `rollup_visitors` cron), instead of only when a month
  finalises — so digests no longer linger up to a month past the 396-day cutoff.
- The "Deduplicated within each month" caveat on the Visitors KPI is shown only
  for ranges that actually span more than one month, not on single-month, today,
  or realtime views.
- The retention sweep (`discard_expired_digests`) now has a dedicated partial
  index (`idx_we_visitor_key_expiry`, on `created_at` where `visitor_key IS NOT
  NULL`): its age-only `UPDATE` no longer fell back to a sequential scan of
  `website_event` on every throttled write-path tick.
- A malformed/unparseable visitor period key (only reachable via DB corruption)
  is now skipped with a warning instead of aborting the whole rollup transaction
  and blocking retention housekeeping.
- The write-path rollup computes the finished-window set once per tick (used as
  both the guard and the rollup input) instead of scanning the period keys twice;
  the now-unused `has_unrolled_past_periods` helper was removed.

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
