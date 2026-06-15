# Changelog

All notable changes to Mantecato are documented here.
The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).

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
