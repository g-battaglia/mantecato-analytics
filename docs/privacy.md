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
- coarse device class derived from the User-Agent: `browser`, `os`, `device`
- `country` (ISO-3166 alpha-2 only — never region or city)
- a server timestamp, and a bot classification (`is_bot`, `bot_reason`)
- a random per-event UUID (not linked to any visitor)

## What is **never** stored

- ❌ Cookies or any browser storage (localStorage/sessionStorage/IndexedDB)
- ❌ IP addresses (used transiently, then discarded — see below)
- ❌ Raw User-Agent strings (only the coarse browser/os/device class is kept)
- ❌ Query strings (`?...`) — discarded at ingestion; they can carry PII
- ❌ Referrer, UTM, click IDs, custom-event payloads, `identify()` data
- ❌ Sessions lists, visitor profiles, journeys, session replay, region/city
- ❌ Any persistent or cross-site visitor/session identifier

## How exact visitor/visit/bounce counts work (compute-and-discard)

To count uniques exactly **without** a stored identifier, Mantecato uses a
compute-and-discard scheme:

1. A **random salt** is generated for each UTC day and shared across workers.
2. On each pageview the server computes
   `HMAC-SHA256(daily_salt, website_id + IP + User-Agent)` — an ephemeral
   per-day digest. The IP and User-Agent are used only for this computation and
   are **not stored**.
3. The digest deduplicates a visitor **within that day only** and updates small
   integer counters (visits, bounces, pageviews, on-site seconds).
4. A nightly **rollup** folds those counters into permanent, fully anonymous
   daily totals (`visitor_daily`) and **deletes** the day's digests *and its
   salt*. Once the salt is gone the digests can never be recomputed or linked
   (forward secrecy). No cross-day or returning-visitor linkage is possible.

The salt is independent from `SECRET_KEY`.

### What "exact" means

- **Visits** and **bounce rate** are additive → exact for any date range.
- **Unique visitors** are exact **per day**. For a multi-day range the figure is
  the **sum of daily uniques**, so a person visiting on several days is counted
  once per day. Exact cross-day uniques / returning visitors are intentionally
  **not** offered (they would require a persistent identifier, i.e. consent).
- Visitor/visit metrics are shown only without a content/device/geo filter; with
  such a filter active they read `N/A` (aggregates cannot be sliced by those
  dimensions without re-introducing per-person data).

## Retention

- Ephemeral per-day digests (`visitor_day_state`) and the daily salt
  (`visitor_day_salt`) exist for at most ~24h and are deleted by the rollup.
  The rollup runs automatically (throttled, piggybacked on ingestion) and on
  each deploy. **For a strict ≤24h guarantee, schedule it daily**, e.g. a
  Railway Cron / Render Cron Job / system cron running:

  ```
  python manage.py rollup_visitors
  ```

- `website_event` rows are anonymous aggregates with no identifier; they are
  kept until you purge them. A per-site purge is available in Settings.

## Do Not Track / Global Privacy Control

The tracker honours DNT and GPC **by default** (opt out per site with
`data-do-not-track="false"`). GPC is treated as a binding opt-out signal
(CCPA/CPRA).

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
> coarse device type, and country). Because nothing is stored on your device and
> no profile is built, no consent banner is required. We honour Do Not Track and
> Global Privacy Control signals.
