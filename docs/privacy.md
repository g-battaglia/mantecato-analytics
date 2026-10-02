# Mantecato — Privacy & data facts

> This document describes how Mantecato processes data so operators can run it
> consent-free and write an accurate privacy notice. It is engineering
> documentation, **not legal advice** — have counsel confirm before publishing a
> "GDPR-compliant" claim for your specific deployment. For a field-by-field data
> inventory ready to hand to an authority, see
> [data-processing-record.md](data-processing-record.md).

The **tracked-site collector** is cookieless. Operator login/consent uses signed
session and CSRF cookies separately. Optional [AI connections](AI-CONNECTIONS.md)
are available when the server's public URL is configured and require explicit
site-scoped approval before sharing requested aggregates with an external
assistant; they do not change tracker collection or formulas.

Mantecato's tracker is **cookieless** and stores **no persistent per-person identifier**.
It measures aggregate web traffic and produces **exact** daily counts of
visitors, visits and bounce rate without cookies, browser storage, fingerprint
persistence, or cross-site/cross-month tracking.

## What is collected

For every pageview the server records one row (`website_event`) with:

- `url_path` (path only — see below), `page_title`, `hostname`
- `content_groups`: optional labels the **site owner** declares for the page on
  the tracker tag (`data-groups="cat:guides,tag:python"`). They describe the
  *page*, exactly like its title, and are fixed at build time by the site:
  nothing about the visitor is read, inferred or stored to produce them. A site
  that sets no labels stores none. Capped at 12 labels of 96 characters, which
  the server enforces. Operators must not put personal data in a label — see "Operator
  responsibilities"
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

## What the tracked-site collector **never** stores

- ❌ Cookies or any browser storage (localStorage/sessionStorage/IndexedDB)
- ❌ IP addresses (used transiently, then discarded — see below)
- ❌ Raw User-Agent strings (only the coarse browser/os/device class is kept)
- ❌ Query strings (`?...`) — discarded at ingestion; they can carry PII/tokens.
  URL fragments (`#...`) are dropped too, **except** a token-free hash-based SPA
  route (`#/...`, no `=`/`&`), which is kept as part of the page path
- ❌ Full referrer URLs (only the bare domain is kept), UTM/click IDs,
  custom-event payloads, `identify()` data. Content groups are not an exception:
  they are page metadata set by the site, not a per-visitor property
- ❌ Sessions lists, visitor profiles, journeys, session replay, region/city
- ❌ Any persistent or cross-site visitor/session identifier

## How exact visitor/visit/bounce counts work (compute-and-discard)

To count uniques exactly **without** a stored identifier, Mantecato uses a
compute-and-discard scheme:

1. A **random salt** is generated for each **calendar month** and shared across
   workers. The dedup window is **fixed at one month** (not configurable): a
   returning visitor is counted once per month, and over a multi-month range the
   per-month uniques are summed (no cross-month linkage). The monthly salt is a
   fixed calendar period well under the 13-month identifier ceiling and never
   renews per visit.
2. On each pageview the server computes
   `HMAC-SHA256(month_salt, website_id + truncated_IP + User-Agent)` — an ephemeral
   digest. The IP and User-Agent are used only for this computation and are
   **not stored**. The IP is **always truncated** to `/24` (IPv4) / `/48` (IPv6)
   before hashing so the digest cannot become a precise fingerprint — the
   IP-minimisation condition the CNIL/Garante exemption requires, applied
   unconditionally. Geo (country) and datacenter-bot detection still use the full IP.
3. The digest deduplicates a visitor **within that month only**. It updates
   small integer counters (visits, bounces, on-site seconds) and is also stored
   on the event row (`website_event.visitor_key`) so unique visitors can be
   counted exactly at **any** time granularity (e.g. per hour) and in realtime
   ("visitors online"). The digest is not an IP/UA and is not reversible without
   the salt.
4. An **offline daily rollup** folds finished-window counters into permanent
   anonymous aggregates (`visitor_daily` per day, `visitor_period` per window).
   Each site's aggregates and state deletion commit together. The window's salt
   is deleted only once no site's day/scope state remains. Separately, digests
   older than **396 days** are NULLed in bounded batches; event rows are never
   deleted by maintenance. No cross-month or returning-visitor linkage is added.

The salt is independent from `SECRET_KEY`. The event log carries a monthly
pseudonymous digest, retained for **396 days** (fixed, not configurable) so visitor
metrics remain exact and **filterable** at read time. After a finished window is
fully rolled up, its salt is discarded and its digest cannot be recomputed from
an IP/User-Agent. Salt destruction is not automatic at midnight: it depends on
a successful offline job. Neither HTTP requests nor deployment/web startup runs
rollup or retention. Schedule and monitor daily `run_daily_maintenance`, which includes visitor rollup
and independent AI credential/audit cleanup.

**Imported data:** the Umami importer hashes each event's `session_id` into the
same `visitor_key`, so imported pageviews carry visitor attribution; the import
sessionises those into the permanent aggregates and then discards the digests
(`backfill_visitor_aggregates` does the same for an existing import).

### What "exact" means

- **Visits** and **bounce rate** are additive → exact for any date range.
- **Unique visitors** are exact **within a calendar month** and for any sub-range
  with retained digests. A range spanning several months sums per-month uniques.
  The API's separately named `daily_unique_visitors` sums daily uniques. Exact
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

- The per-event digest (`website_event.visitor_key`) is retained for **396 days**,
  then **NULLed**, independently of whether rollup has completed. The fixed
  retention is not an environment setting. Monthly salts are deleted after all
  finished-window state has been finalized, not necessarily at midnight.
- Run a separate daily Railway/Render/system cron:

  ```bash
  python manage.py run_daily_maintenance --rollup-runtime 900 --ai-runtime 120 --sql-timeout-ms 60000
  ```

  Monitor job success, finished-period backlog and pending expired digests.
  A dry-run performs no writes. Requests and web startup never provide a fallback
  scheduler. See [Railway](RAILWAY.md#e-daily-maintenance-required).
- `website_event` rows remain stored after digest expiry. A per-site purge is
  available in Settings.

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

## Why the default tracker can run without a cookie banner

The cookie-banner trigger comes from **ePrivacy Art. 5(3) / UK PECR**, which
govern *storing or accessing information on the terminal device*. With the
default tracked-site script (`credentials: "omit"`, no cookies, no browser
storage, no device-storage reads), Mantecato does not perform that terminal
storage/access. That is the technical basis for running the tracker without a
cookie banner.

This is deployment-dependent: keep `credentials: "omit"` /
`data-fetch-credentials="omit"` and strip inbound `Cookie` headers at any
same-origin reverse proxy for the collector. If you intentionally send/read
cookies, add browser storage, or combine Mantecato with advertising/cross-site
tracking, reassess consent before claiming "no banner".

This does **not** remove privacy-law duties. The transient IP + User-Agent
processing and the live visitor digest still need transparency and a lawful
basis. Mantecato fixes the privacy-critical parameters so the basis cannot be
misconfigured — they are **not configurable**:

- **Dedup window = one calendar month**, never renewed per visit. Salt destruction
  follows successful offline finalization; operators must monitor job failures.
- **IP always truncated** to `/24` (IPv4) / `/48` (IPv6) before hashing.
- **Digest retention = 396 days (~13 months)**, then NULLed; aggregates are anonymous.

On that fixed footing the **EU/UK** basis is the DPA **consent-exempt
audience-measurement** route (CNIL *Sheet 16*; Italian *Garante* 2021), whose
conditions Mantecato meets by construction:

- first-party / single site, **no cross-referencing**, no cross-site tracking ✓
- aggregate-only output, country-level geo (no precise location) ✓
- **identifier lifetime ≤ 13 months, no per-visit renewal** ✓ (fixed monthly salt)
- **IP truncation** (CNIL: last IPv4 byte; Garante: ≥ 4th octet) ✓ (always on)
- data retention ≤ 25 months ✓ (digests NULLed at ~13 months; aggregates anonymous)
- **transparency + opt-out** — publish the notice below and keep GPC honoured ✓

Document a short legitimate-interest assessment (LIA, GDPR Art. 6(1)(f)) and,
because the monthly digest is a time-limited identifier, a **DPIA**; have counsel
confirm before making a consent-free claim, especially for Italy.

- **US / Canada / Australia**: the usual issue is transparency, meaningful
  consent or opt-out where applicable, not a classic EU-style cookie banner for a
  no-storage first-party analytics script. Keep the privacy notice accurate, do
  not sell/share or use the data for cross-context advertising, and keep GPC
  honoured.

## Optional AI data sharing

Consent authorizes later read-only aggregate requests for explicitly selected
sites, never automatic access to future sites. It does not upload the database,
but requested paths, titles, groups and event names can contain personal data.
The chosen client/provider receives results and may retain them; check the actual
account's training, sharing, retention and legal terms. Revocation stops future
reads/refresh but cannot erase already received copies. No universal provider
retention, training exclusion or DPA promise applies.

AI authentication stores opaque credential digests, explicit site/scopes,
expiry and a password-auth fingerprint. Consent evidence is a version and
canonical-text hash. Metadata-only activity records operation, site UUID,
connection/owner, timestamp and outcome, never prompts, arguments/results,
raw credentials or IP addresses. Audit is retained up to 90 days through the
separate cleanup job; expiry/revocation checks do not depend on that job.
Personal tokens appear once with no-store/history protection, never in setup
prompts or browser storage. They default to 30 days, with an explicit no-expiry
option; valid no-expiry credentials are retained until revocation/account deletion
rather than age-expired. Live access, password and server-identity checks still
apply. OAuth credentials remain time-limited. Operator cookies are not visitor-tracking cookies.
See [AI connections](AI-CONNECTIONS.md) before activating external sharing.

## Operator responsibilities

1. Publish a privacy notice describing the above (template below).
2. Record a short **Legitimate Interest Assessment (LIA)** and a **DPIA** for the
   transient IP/User-Agent processing and the monthly digest (a time-limited
   identifier). The window, IP truncation and retention are fixed, so there is
   nothing to tune — just document them.
3. Schedule `run_daily_maintenance` daily for the strict retention guarantee.
4. Keep tracker fetch credentials at `omit`; if the collector is reverse-proxied
   under the tracked site's origin, strip inbound `Cookie` headers before the
   request reaches Mantecato.
5. Keep `SECRET_KEY` secret and set a restrictive `ALLOWED_HOSTS` in production.
6. If you use **content groups**, label pages by topic only. Ingestion
   lowercases each label, trims surrounding whitespace, drops duplicates, cuts
   it to 96 characters and keeps at most 12 per page — it does not inspect or
   redact what the label *says*, and the normalised value is what appears in the
   dashboard and in exports. So never derive a label from the visitor (their
   plan, cohort, referrer or anything they typed) and never put personal data in
   one. A label is a property of the page; the moment it varies per person it
   stops being one, and the consent-free posture described above no longer
   covers it.

## Model privacy-notice snippet (for site owners)

> Mantecato deduplicates returning visitors within a **calendar month** using an
> in-month digest. Its salt is destroyed after offline finalization, while
> event digests expire after 396 days; the wording below reflects that.

> We use Mantecato, a privacy-first, cookieless analytics tool, to measure
> aggregate traffic on this site. It does not use cookies or browser storage and
> does not store your IP address, your full browser User-Agent, or any
> identifier that can recognise you across months or across sites. We only see
> anonymous, aggregate statistics (e.g. total pageviews and visits, bounce rate,
> average time on page, coarse device type, country, and the domain of the site
> that referred you — never the full address). Because this analytics tool stores
> nothing on your device and builds no profile, we do not use an analytics cookie
> banner for it. We honour Global Privacy Control (GPC) opt-out signals.
