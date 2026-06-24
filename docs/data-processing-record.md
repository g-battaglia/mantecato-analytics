# Data Processing Record — what Mantecato collects and how

> Authority-ready inventory of every piece of data the default Mantecato tracker
> touches: what reaches the server, what is used transiently and discarded, and
> what is actually stored. Pair this with [privacy.md](privacy.md) (legal basis,
> why no consent banner) when responding to a GDPR / Garante / ICO / CCPA / OPC /
> OAIC enquiry. It reflects the shipped default configuration.
>
> **Roles (GDPR Art. 4 / 24/28):** Mantecato is self-hosted. The site operator
> running the instance is the **data controller**; Mantecato is the software, not a
> third-party processor — no data leaves the operator's own infrastructure.
> **This is engineering-for-compliance documentation, not legal advice.**

## 1. Fixed privacy posture (not configurable)

These parameters are hardcoded so the posture cannot be misconfigured:

| Parameter | Fixed value | Why |
|---|---|---|
| Cookies / browser storage | **none** (no cookie, localStorage, sessionStorage, IndexedDB) | No ePrivacy Art. 5(3) / PECR storage-or-access trigger → no cookie banner |
| Dedup window | **1 calendar month** | Salt rotates monthly, discarded at month end; identifier ≤ ~31 days |
| IP truncation (digest input) | **always /24 (IPv4) + /48 (IPv6)** | CNIL/Garante IP-minimisation, applied unconditionally |
| Digest retention | **396 days (~13 months)** then NULLed | CNIL ceiling for a consent-free audience identifier |
| Global Privacy Control (GPC) | **honoured by default** (server + client) | Valid opt-out under CCPA/CPRA and US state laws |

## 2. What the browser sends (the tracked-site script)

The client script (`@mantecato/tracker`) runs with `credentials: "omit"` (never
sends cookies) and transmits, per pageview/event, only:

| Sent value | Example | Notes |
|---|---|---|
| Website ID | `a0000000-…` | Identifies the operator's site, not the visitor |
| Page path | `/pricing` | Query string `?…` is **dropped** (may carry tokens); URL fragment `#…` is dropped too, except a token-free SPA route (`#/…`) which is kept as part of the path |
| Page title | `Pricing` | |
| Referrer | `https://google.com/…` | Reduced server-side to **domain only**; same-site dropped |
| Hostname | `example.com` | The tracked site |
| Engagement seconds | `42` | Active on-page time (heartbeat), for duration/bounce |

The script reads `navigator.userAgent`, `navigator.globalPrivacyControl`,
`navigator.doNotTrack` and `navigator.webdriver` **only on the device** for
client-side bot detection and opt-out, and **does not transmit them** (so this
reading does not "leave the device" — outside ePrivacy Art. 5(3) per EDPB
Guidelines 2/2023 §44).

## 3. What the server does with the request — transient vs stored

The server additionally sees, from the HTTP request itself, the **client IP** and
**User-Agent header**. These are **used transiently and never stored**:

| Transient input | Used for | Then |
|---|---|---|
| Client IP | (a) visitor digest after `/24`–`/48` truncation; (b) country lookup; (c) datacenter-bot detection; (d) in-memory rate-limit key | **Discarded** — never written to any table |
| User-Agent (header) | (a) visitor digest; (b) parse to browser/OS/device family; (c) bot classification | **Discarded** — only the parsed families are stored |
| `Sec-GPC` / `DNT` headers | server-side opt-out | A `Sec-GPC: 1` request is **dropped, not counted** |

The visitor digest is `HMAC-SHA256(monthly_random_salt, website_id | truncated_IP |
User-Agent)`. The salt is random, shared across workers, and **deleted by the
rollup at month end** → after that the digest can never be recomputed or linked to
an IP/UA (forward secrecy).

## 4. What is actually stored (data inventory)

### 4.1 `website_event` — one row per pageview/custom event

| Field | Example | Personal data? | Notes |
|---|---|---|---|
| `event_id` | UUID | No | Random per-event ID, not per-person |
| `website_id` | UUID | No | The site |
| `created_at` | timestamp | No | Event time |
| `url_path` | `/pricing` | No | Path only |
| `url_query` | `NULL` | — | **Always NULL** (never populated) |
| `page_title` | `Pricing` | No | |
| `event_type` / `event_name` | `1` / `signup` | No | Pageview vs named custom event (no payload/properties) |
| `hostname` | `example.com` | No | |
| `browser` / `os` / `device` | `Chrome` / `Mac OS X` / `desktop` | No | Parsed family, ≤ 20 chars each; raw UA not stored |
| `country` | `IT` | No | ISO 3166-1 alpha-2 **only** (no region/city/coords) |
| `is_bot` / `bot_reason` | `false` / `null` | No | Aggregate bot classification |
| `referrer_domain` | `google.com` | No | Domain only; no full URL, no UTM/click IDs |
| `visitor_key` | 64-hex HMAC | **Pseudonymous** while the month's salt lives; **anonymous** once NULLed (≤13 months) | The only per-person field; a salted dedup digest, not an IP/UA, not reversible without the salt |

### 4.2 Supporting tables
- `visitor_salt` — the per-month random salt; **deleted** at month end.
- `visitor_day_state` / `visitor_scope_state` — ephemeral counters; deleted at rollup.
- `visitor_daily` / `visitor_period` — **permanent anonymous aggregates** (integer
  counts of unique visitors, visits, bounces, pageviews, seconds). No per-person field.

## 5. What is explicitly NOT collected

No cookies or any device storage; no IP address stored; no full User-Agent stored;
no `session_id`/`visit_id`; no persistent or cross-day/cross-site identifier; no
cross-site or cross-device tracking; no fingerprinting; no precise geolocation
(country only); no full referrer URL, UTM parameters or click IDs; no event payload
/ form contents / custom properties; no name, email, account or device IDs; no data
sale or sharing; no third-party processors; no international transfer (self-hosted).

## 6. Legal basis (summary — details in privacy.md)

- **EU/UK (GDPR/UK GDPR + ePrivacy/PECR):** no device storage/access → **no consent
  banner**. Transient truncated-IP + UA processing rests on the **consent-exempt
  audience-measurement** basis (CNIL Sheet 16; Garante 2021) — first-party, IP
  masked, ≤13-month identifier, ≤25-month retention, country geo, transparency +
  GPC — all met by construction. Operator documents an **LIA + DPIA**.
- **US (CCPA/CPRA + state laws):** no cookie-banner regime; no sale/share/targeted
  advertising; **GPC honoured**. Requirement met by a **privacy policy** disclosure.
- **Canada (PIPEDA + Québec Law 25):** no banner; first-party non-sensitive analytics
  via transparency; Law 25 Art. 8.1 profiling/location tech **not triggered** (aggregate
  only, country geo). Requirement: a clear privacy notice.
- **Australia (Privacy Act 1988 + APPs):** no banner; consent only for sensitive data
  (none collected). Requirement: an **APP 5** notice + data minimisation (met).

## 7. Retention, rights, security

- **Retention:** `visitor_key` digest NULLed at **396 days**; aggregates are anonymous
  and permanent. The monthly salt is destroyed at month end. Run `manage.py
  rollup_visitors` daily to enforce this.
- **Data-subject rights:** because no stored field identifies a person (the digest is
  pseudonymous only while the month's salt exists, then anonymous), there is normally
  no data to access/erase/rectify per-person; document this position. Honour GPC/opt-out.
- **Security:** HMAC-SHA256 digests, salt independent of `SECRET_KEY`, TLS in transit,
  operator-controlled `ALLOWED_HOSTS`/`DEBUG`, configurable `TRUSTED_PROXY_COUNT` for
  correct client-IP handling.

## 8. Operator checklist for an authority enquiry

1. Provide this record + [privacy.md](privacy.md).
2. Show the published privacy notice (template in privacy.md) and the LIA/DPIA.
3. Confirm `rollup_visitors` runs daily (retention) and GPC is honoured.
4. Confirm no third parties, no sale/share, no advertising integration were added.
