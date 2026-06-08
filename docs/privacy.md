# Mantecato — Privacy & data facts

> This document describes how Mantecato processes data so operators can run it
> consent-free and write an accurate privacy notice. It is engineering
> documentation, **not legal advice** — have counsel confirm before publishing a
> "GDPR-compliant" claim for your specific deployment.

Mantecato is **cookieless** and stores **no persistent per-person identifier**.
It measures aggregate web traffic and produces **exact** daily counts of
visitors, visits and bounce rate without cookies, browser storage, fingerprint
persistence, or cross-site/cross-day tracking.

## What is collected

For every pageview the server records one anonymous row (`website_event`) with:

- `url_path` (path only — see below), `page_title`, `hostname`
- the referrer **domain** only (e.g. `google.com`) — never the full referrer
  URL, its query string, or any UTM/click ID; same-site referrals are dropped
- coarse device class derived from the User-Agent: `browser`, `os`, `device`
- `country` (ISO-3166 alpha-2 only — never region or city)
- a server timestamp, and a bot classification (`is_bot`, `bot_reason`; the
  reason may be `datacenter_ip` — see "Bot filtering" below)
- a random per-event UUID (not linked to any visitor)

Separately, small per-visit integer counters track **active on-page time**
(engagement) for accurate visit duration and the "engaged bounce" rate. No
per-event timing log or scroll map is kept — only the aggregate seconds.

## What is **never** stored

- ❌ Cookies or any browser storage (localStorage/sessionStorage/IndexedDB)
- ❌ IP addresses (used transiently, then discarded — see below)
- ❌ Raw User-Agent strings (only the coarse browser/os/device class is kept)
- ❌ Query strings (`?...`) — discarded at ingestion; they can carry PII
- ❌ Full referrer URLs (only the bare domain is kept), UTM/click IDs,
  custom-event payloads, `identify()` data
- ❌ Sessions lists, visitor profiles, journeys, session replay, region/city
- ❌ Any persistent or cross-site visitor/session identifier

## How exact visitor/visit/bounce counts work (compute-and-discard)

To count uniques exactly **without** a stored identifier, Mantecato uses a
compute-and-discard scheme:

1. A **random salt** is generated for each **exactness window** and shared
   across workers. The window is `day`, `week` or `month`
   (`VISITOR_EXACT_WINDOW`, **default `day`** → unique visitors over a range are
   the sum of daily uniques, the conventional figure).
2. On each pageview the server computes
   `HMAC-SHA256(window_salt, website_id + IP + User-Agent)` — an ephemeral
   digest. The IP and User-Agent are used only for this computation and are
   **not stored**.
3. The digest deduplicates a visitor **within that window only**. It updates
   small integer counters (visits, bounces, on-site seconds) and is also stored
   on the event row (`website_event.visitor_key`) so unique visitors can be
   counted exactly at **any** time granularity (e.g. per hour) and in realtime
   ("visitors online"). The digest is not an IP/UA and is not reversible without
   the salt.
4. A **rollup** folds the counters into permanent, fully anonymous aggregates
   (`visitor_daily` per day, `visitor_period` per window — exact window uniques),
   **deletes** the window's salt and ephemeral state, and **NULLs the per-event
   digests** of finalised windows. Once the salt is gone and the digests are
   nulled they can never be recomputed or linked (forward secrecy). No
   cross-window or returning-visitor linkage is possible; finalised event rows
   are fully anonymous.

The salt is independent from `SECRET_KEY`. During the live window the event log
carries the window digest (pseudonymous within the window); the rollup discards
it once the day is finalised. `VISITOR_KEY_RETENTION_DAYS` (default 2) bounds how
long digests are kept for fine-grained (hourly/realtime) reads before the day is
aggregated and the digests nulled — schedule `rollup_visitors` to enforce it.

**Imported data:** the Umami importer hashes each event's `session_id` into the
same `visitor_key`, so imported pageviews carry visitor attribution; the import
sessionises those into the permanent aggregates and then discards the digests
(`backfill_visitor_aggregates` does the same for an existing import).

### What "exact" means

- **Visits** and **bounce rate** are additive → exact for any date range.
- **Unique visitors** are exact **for the exactness window** (default `day`) and
  for any sub-range of the live window. A range spanning several windows sums
  per-window uniques (with the day default, the sum of daily uniques). Exact
  cross-window uniques / returning visitors are intentionally **not** offered —
  they need a persistent identifier (consent).
- Per-page / per-section / per-event unique visitors are exact for the window.
- Visitor/visit metrics are shown only without a content/device/geo filter; with
  such a filter active they read `N/A` (aggregates cannot be sliced by those
  dimensions without re-introducing per-person data).

### The cookieless ceiling (honest limit)

"Exact" is over the salted **IP + User-Agent** token, not over a human. Across a
long window an IP can change (mobile / DHCP / home↔office), so the same person
may be counted more than once, and people sharing an IP+UA may merge. The longer
the window, the more this drifts. Tracking a *person* over time would require a
persistent identifier (a cookie + consent), which Mantecato deliberately avoids.
This ceiling applies to every cookieless analytics tool.

## Retention

- Ephemeral digests (`visitor_day_state`, `visitor_scope_state`, and the
  per-event `website_event.visitor_key`) plus the window salt (`visitor_salt`)
  are kept at most ~`VISITOR_KEY_RETENTION_DAYS` (default 2 days) before the
  rollup aggregates the day into the permanent anonymous aggregates and discards
  them. The rollup runs automatically (throttled, piggybacked on ingestion) and
  on each deploy. **For a strict guarantee, schedule it**, e.g. a Railway Cron /
  Render Cron Job / system cron running:

  ```
  python manage.py rollup_visitors
  ```

  Trade-off: a longer window gives more precise unique counts (e.g. exact
  monthly visitors) but keeps the anonymous dedup state at rest for that long.

- `website_event` rows are anonymous aggregates with no identifier; they are
  kept until you purge them. A per-site purge is available in Settings.

## Do Not Track / Global Privacy Control

The tracker honours DNT and GPC **by default** (opt out per site with
`data-do-not-track="false"`). GPC is treated as a binding opt-out signal
(CCPA/CPRA).

## Bot filtering

Known bots are excluded by User-Agent pattern, and requests from cloud/datacenter
IP ranges are flagged (`bot_reason = datacenter_ip`) using a **bundled** CIDR list
— no third-party service is contacted, and the IP is used only transiently (never
stored, exactly as for visitor counting). Datacenter detection can be disabled
(`DETECT_DATACENTER_IPS=false`) and the CIDR list extended (`DATACENTER_CIDRS`).
Bot hits never enter the visitor/visit counts and are excluded from pageview
breakdowns when bot filtering is enabled for a site.

When a per-site bot config enables behavioural rules (zero-engagement,
high-velocity, datacentre clusters, excluded countries), those run **at
aggregation time** on the window digest — the cookieless equivalent of a session —
so the bot filter reduces the exact **visitor/visit/bounce** counts too, not only
pageviews. The digest is discarded as usual; only anonymous integer counts remain.

## Why no consent banner is required

- **ePrivacy Art. 5(3) / UK PECR**: these govern *storing or accessing
  information on the terminal device*. Mantecato sets nothing on the device and
  reads no device storage, so the cookie-consent rule is not triggered.
- **GDPR / UK GDPR**: the transient processing of IP + User-Agent to derive the
  discarded digest is first-party, single-purpose audience measurement on a
  **legitimate-interest** basis, aligned with the consent-exemption criteria
  used by DPAs such as the CNIL (first-party, anonymous statistics, no
  cross-referencing, no cross-site tracking, no precise location).
- **Italy / Garante**: first-party anonymised audience measurement.
- **US (CCPA/CPRA & state laws)**: no sale/share, no cross-context identifier,
  GPC honoured.

## Operator responsibilities

1. Publish a privacy notice describing the above (template below).
2. Record a short **Legitimate Interest Assessment (LIA)** for the transient
   IP/User-Agent processing.
3. Schedule `rollup_visitors` daily for the strict retention guarantee.
4. Keep `SECRET_KEY` secret and set a restrictive `ALLOWED_HOSTS` in production.

## Model privacy-notice snippet (for site owners)

> We use Mantecato, a privacy-first, cookieless analytics tool, to measure
> aggregate traffic on this site. It does not use cookies or browser storage and
> does not store your IP address, your full browser User-Agent, or any
> identifier that can recognise you across days or across sites. We only see
> anonymous, aggregate statistics (e.g. total pageviews and visits, bounce rate,
> average time on page, coarse device type, country, and the domain of the site
> that referred you — never the full address). Because nothing is stored on your device and
> no profile is built, no consent banner is required. We honour Do Not Track and
> Global Privacy Control signals.
