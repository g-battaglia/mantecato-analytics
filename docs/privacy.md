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

1. A **random salt** is generated for each **dedup window** and shared
   across workers. The window is `day`, `week`, `month`, `quarter` or `year`
   (`VISITOR_EXACT_WINDOW`, **default `day`** → unique visitors over a range are
   the sum of daily uniques, the conventional figure). A longer window
   deduplicates returning visitors across more days — the salt, and therefore the
   identifier lifetime, lasts as long as the window. All windows are **fixed
   calendar periods ≤ 13 months with no per-visit renewal**. **Choosing a window
   longer than `day` changes the legal basis — see "Why no consent banner".**
2. On each pageview the server computes
   `HMAC-SHA256(window_salt, website_id + IP + User-Agent)` — an ephemeral
   digest. The IP and User-Agent are used only for this computation and are
   **not stored**. The IP is first **truncated** (`VISITOR_HASH_IP_PREFIX_V4` /
   `_V6`, default `auto`: the full IP only for the `day` window, `/24` + `/48` for
   any longer window) so a longer-lived digest cannot become a precise
   fingerprint — the IP-minimisation condition the CNIL/Garante exemption
   requires. Geo (country) and datacenter-bot detection still use the full IP.
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
it once the digest ages past retention. `VISITOR_KEY_RETENTION_DAYS` (default
**396 ≈ 13 months**, the CNIL ceiling for a consent-free audience-measurement
identifier) bounds how long the digests are kept so visitor metrics stay exact
and **filterable** at read time; after that the rollup folds the data into the
permanent anonymous aggregates and nulls the digests — schedule `rollup_visitors`.
The **salt is still discarded at window end**, so a retained digest from a past
window can no longer be re-linked to an IP/User-Agent.

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
- Per-page / per-section / per-entry-page / per-event unique visitors (and the
  landing-page visits/bounce table) are computed from the digests at read time as
  well, so they slice under the same filters — exact within the retention window.
- Visitor/visit metrics are computed from the event digests **at read time**, so a
  content/device/geo/bot filter slices them downstream too (within the retention
  window) — the stored data never changes. Ranges reaching past retention fold in
  the dimensionless anonymous aggregates, which are not filterable for those days.

### The cookieless ceiling (honest limit)

"Exact" is over the salted **IP + User-Agent** token, not over a human. Across a
long window an IP can change (mobile / DHCP / home↔office), so the same person
may be counted more than once, and people sharing an IP+UA may merge. The longer
the window, the more this drifts. Tracking a *person* over time would require a
persistent identifier (a cookie + consent), which Mantecato deliberately avoids.
This ceiling applies to every cookieless analytics tool.

## Retention

- The per-event digest (`website_event.visitor_key`) is kept for
  ~`VISITOR_KEY_RETENTION_DAYS` (default **396 ≈ 13 months**) so visitor metrics
  stay exact and filterable at read time, then the rollup folds the data into the
  permanent anonymous aggregates and **NULLs the digest**. The window **salt** is
  discarded much sooner (at window end), so a retained digest from a past window
  is no longer re-linkable to an IP/User-Agent — the extra-retained data is an
  unlinkable token. The rollup runs automatically (throttled, on each deploy);
  **for a strict guarantee, schedule it** (Railway/Render/system cron):

  ```
  python manage.py rollup_visitors
  ```

  Trade-off: a longer retention keeps richer (filterable) history but holds the
  pseudonymous digests at rest for that long. 13 months is the consent-free
  audience-measurement ceiling; lower it via the env var if you want less.

- `website_event` rows are anonymous aggregates with no identifier; they are
  kept until you purge them. A per-site purge is available in Settings.

## Do Not Track / Global Privacy Control

The tracker honours **Global Privacy Control (GPC) by default** — GPC is a
legally-recognised opt-out signal under CCPA/CPRA and several US state privacy
laws. Opt out per site with `data-respect-gpc="false"`.

The legacy **Do Not Track (DNT)** header is **not** legally binding (abandoned
W3C standard) and is **ignored by default**, matching Umami. Opt in per site with
`data-do-not-track="true"`.

## Bot filtering

At ingestion each event is tagged with a coarse bot classification: known bots by
User-Agent pattern, and cloud/datacenter source IPs (`bot_reason = datacenter_ip`)
via a **bundled** CIDR list — no third-party service is contacted, and the IP is
used only transiently (never stored). Datacenter detection can be disabled
(`DETECT_DATACENTER_IPS=false`) and the CIDR list extended (`DATACENTER_CIDRS`).

The bot filter is a **non-destructive, downstream (read-time) filter** — exactly
like the session-based product: the stored data never changes, and toggling it
re-computes the metrics. With it **off** every hit is counted; **on**, the bot
rows (and, via the per-site config, excluded countries) are filtered out. Because
visitor/visit counts are computed from the event digests at read time, the filter
moves **all** of them — pageviews, visitors, visits and bounce — not just
pageviews.

## Why no consent banner is required

The banner requirement comes from **ePrivacy Art. 5(3) / UK PECR**, which govern
*storing or accessing information on the terminal device*. Mantecato sets nothing
on the device and reads no device storage, so that rule is **not triggered —
whatever the dedup-window length**. The window length instead determines the
**GDPR basis** for the transient IP + User-Agent processing:

- **`day` window (default) — "no persistent identifier".** The salt is discarded
  every 24h, so a visitor cannot be linked from one day to the next; there is no
  persistent identifier at all and legitimate interest (GDPR Art. 6(1)(f)) applies
  trivially. This is the Plausible/Fathom posture.
- **Window longer than `day` — "consent-exempt audience measurement".** The salt
  (identifier) now persists for the window, so the basis shifts to the DPA
  audience-measurement exemption (CNIL *Sheet 16*; Italian *Garante* 2021, which
  treats first-party analytics as consent-exempt in principle). That exemption is
  **conditional** — all of the following must hold, and Mantecato is built to:
  - first-party / single site, **no cross-referencing**, no cross-site tracking ✓
  - aggregate-only output, country-level geo (no precise location) ✓
  - **identifier lifetime ≤ 13 months, no per-visit renewal** ✓ (fixed windows ≤ 1 year)
  - **IP truncation** (CNIL: last IPv4 byte; Garante: ≥ 4th octet) ✓ (auto at > `day`)
  - data retention ≤ 25 months ✓ (digests nulled at ~13 months; aggregates anonymous)
  - **transparency + opt-out** — publish the notice below and keep GPC honoured ✓

  EDPB *Guidelines 2/2023* treat persistent fingerprinting and some IP tracking as
  in-scope of Art. 5(3); the audience-measurement exemption is the route that keeps
  a longer-lived first-party digest consent-free. For windows longer than `day`,
  record a **DPIA** in addition to the LIA, keep IP truncation on (especially for
  Italy), and have counsel confirm.
- **US (CCPA/CPRA & state laws)**: no sale/share, no cross-context identifier,
  GPC honoured.

## Operator responsibilities

1. Publish a privacy notice describing the above (template below).
2. Record a short **Legitimate Interest Assessment (LIA)** for the transient
   IP/User-Agent processing. If you set `VISITOR_EXACT_WINDOW` longer than `day`,
   also record a **DPIA** (the digest is then a time-limited identifier) and keep
   IP truncation on (`VISITOR_HASH_IP_PREFIX_*=auto` or `24`/`48`).
3. Schedule `rollup_visitors` daily for the strict retention guarantee.
4. Keep `SECRET_KEY` secret and set a restrictive `ALLOWED_HOSTS` in production.

## Model privacy-notice snippet (for site owners)

> The wording below matches the **default `day` window** (no cross-day identifier).
> If you run a longer `VISITOR_EXACT_WINDOW`, adjust the "across days" clause to say
> the anonymous in-window digest deduplicates returning visitors within the window
> (e.g. within a calendar month) and is discarded at window end.

> We use Mantecato, a privacy-first, cookieless analytics tool, to measure
> aggregate traffic on this site. It does not use cookies or browser storage and
> does not store your IP address, your full browser User-Agent, or any
> identifier that can recognise you across days or across sites. We only see
> anonymous, aggregate statistics (e.g. total pageviews and visits, bounce rate,
> average time on page, coarse device type, country, and the domain of the site
> that referred you — never the full address). Because nothing is stored on your device and
> no profile is built, no consent banner is required. We honour Global Privacy
> Control (GPC) opt-out signals.
