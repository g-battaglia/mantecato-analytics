# Changelog

All notable changes to Mantecato are documented here.
The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- **Configurable visitor dedup window**: `VISITOR_EXACT_WINDOW` now accepts
  `quarter` and `year` in addition to `day`/`week`/`month`. A longer window
  deduplicates returning visitors across more days (e.g. true monthly uniques)
  instead of summing per-day uniques. All windows are fixed calendar periods
  ≤ 13 months with no per-visit renewal.
- **IP truncation for the visitor digest** (`VISITOR_HASH_IP_PREFIX_V4` / `_V6`,
  default `auto`): keeps the full IP only for the `day` window and truncates to
  `/24` + `/48` for any longer window — the CNIL/Garante IP-minimisation condition
  that keeps a longer-lived first-party digest consent-free. Geolocation and
  datacenter-bot detection still use the full IP.
- Startup warnings for an invalid `VISITOR_EXACT_WINDOW` (falls back to `day`) and
  for a `VISITOR_KEY_RETENTION_DAYS` shorter than the configured window.

### Changed
- The dashboard labels the unique-visitor metric with its dedup window when the
  window is longer than `day`.
- Docs (`docs/privacy.md`, `docs/accuracy.md`): document the two legal bases —
  `day` = "no persistent identifier"; longer windows = the consent-exempt
  audience-measurement basis (CNIL Sheet 16 / Garante), with its conditions
  (≤ 13-month identifier, IP truncation, transparency + opt-out, DPIA).

### Notes
- The shipped default stays `VISITOR_EXACT_WINDOW=day`; the change applies going
  forward (historical digests cannot be retro-deduplicated — the salts are gone).

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
