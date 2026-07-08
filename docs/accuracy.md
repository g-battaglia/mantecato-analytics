# Maximizing tracking accuracy

Mantecato ships **privacy-first defaults**: it honours Global Privacy Control,
classifies bots, and never sets anything on the device. Those defaults are the
right thing to *ship*, but on a **self-hosted, first-party** deployment where you
track **your own apps** and **do not sell or share** data, you can safely turn the
dials toward completeness. This page covers how — from highest to lowest impact.

> Privacy/legal context for the GPC/DNT choices is in [privacy.md](privacy.md).
> The biggest cause of "missing" pageviews in the real world is **ad-blockers**,
> addressed in §2.

## 1. Count privacy opt-out users (GPC / DNT)

The tracker exposes two independent signals (script-tag attributes; the same names
without `data-` exist as `createTracker` options):

| Attribute | Default | Effect |
|---|---|---|
| `data-respect-gpc` | `true` | Skip visitors sending **Global Privacy Control** (e.g. Brave, which sets GPC by default). |
| `data-do-not-track` | `false` | Skip visitors sending the legacy **DNT** header. Off by default (DNT is not legally binding). |

GPC's legal force comes from CCPA/CPRA, which is about **selling/sharing** data. If
you don't sell or share (pure first-party analytics), you can opt out of honouring
it to count those visitors:

```html
<script defer src="/api/script"
  data-website-id="YOUR-UUID"
  data-respect-gpc="false"></script>
```

This recovers the GPC cohort (often a meaningful single-to-double-digit % of
traffic). Decide per your own legal situation — see [privacy.md](privacy.md).

## 2. Serve the tracker first-party (biggest real-world win)

Ad-blockers block analytics by **third-party host and known paths**. Serving the
script and the ingest endpoint from your **app's own origin** via a reverse proxy
makes them first-party and far harder to block. This is a standard, legitimate
self-hosting pattern.

**Critical:** forward the real client IP. Mantecato derives the visitor digest,
geo and bot/datacenter classification from the client IP — if the proxy hides it,
every visitor collapses into one. `get_client_ip` reads `X-Real-IP`,
`X-Forwarded-For` (leftmost), common CDN headers, or a custom `CLIENT_IP_HEADER`.

### nginx (app and Mantecato behind the same domain)

```nginx
location = /api/script {
    proxy_pass http://127.0.0.1:8000;          # your Mantecato instance
}
location = /api/send {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;             # real client IP
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

```html
<!-- Loaded same-origin: baseUrl auto-resolves to your app origin, ingest posts
     to /api/send on the same origin. No data-host-url needed. -->
<script defer src="/api/script" data-website-id="YOUR-UUID"></script>
```

### Caddy

```caddy
handle /api/script {
    reverse_proxy 127.0.0.1:8000
}
handle /api/send {
    reverse_proxy 127.0.0.1:8000 {
        header_up X-Real-IP {remote_host}
    }
}
```

### Neutral paths (extra robustness)

To avoid the literal `/api/send` path, serve under your own paths and point the
tracker at the ingest path with `data-endpoint` (the script `src` is whatever your
proxy maps to `/api/script`):

```html
<script defer src="/assets/m.js" data-website-id="YOUR-UUID" data-endpoint="/collect"></script>
```

with the proxy mapping `/assets/m.js → /api/script` and `/collect → /api/send`.

## 3. Bot filter & datacenter detection

- The dashboard **bot filter is off by default** — every hit (bots included) is
  counted. Leave it off for maximum counts; it is a non-destructive read-time
  toggle you can flip anytime. As of the realtime fix, the live "visitors online"
  widget now follows the same toggle instead of always hiding bots.
- Bots are still *classified* at ingestion (`is_bot` / `bot_reason`) so the toggle
  can work, but classification never drops the stored pageview.
- Datacenter-IP detection (`DETECT_DATACENTER_IPS=true`) can misclassify real
  users on some VPNs/carriers. If you filter bots and see legit users vanish,
  disable it (`DETECT_DATACENTER_IPS=false`) or tune `DATACENTER_CIDRS`.

## 4. Why another tool may report *more* visitors than Mantecato

A lower number is not automatically a *lost* number. When Mantecato shows fewer
visitors than a tool you're migrating from (Umami, GA, a naive full-IP counter),
most of the gap is usually **bot traffic the other tool inflates and Mantecato
deflates** — not real people Mantecato dropped. Two mechanisms dominate, both
confirmed on production data:

- **JS-executing crawlers that pass a user-agent bot filter.** Many tools only
  screen bots *at ingest* by User-Agent and then count everything that got
  through, forever, in every dashboard. A search-engine/rendering crawler that
  isn't on the UA blocklist therefore lands in the "human" numbers (in Umami these
  are the stored `browser='searchbot'` rows — a steady trickle plus occasional
  waves of 1,500–2,000 pageviews/day). Mantecato usually never even receives them:
  the tracker refuses to send when `navigator.webdriver === true`, so headless
  browsers self-exclude on the client.
- **Rotating-IP headless pools counted as one-visitor-per-IP.** A tool that keys a
  session on the **full** client IP treats every IP a datacenter crawler rotates
  through as a brand-new visitor. Measured example: a single content scraper
  (Chrome/Linux, 945 distinct `/content/…` pages crawled in 3 hours) showed up as
  **~457 "visitors"** in a full-IP tool but **1** in Mantecato; a datacenter pool
  produced **1,360 "visitors" for 1,411 pageviews** (1.04 pv/visitor — nobody
  browses like that). Mantecato's `/24` truncation (§5) collapses each pool into a
  single visitor key, and `DETECT_DATACENTER_IPS` flags known ranges outright.

So Mantecato trades a small, honest under-count of privacy-opt-out humans (§1,
GPC) for **not** carrying a large bot over-count in the visitor line. Segment by
country and the two systems agree within a few percent on real human cohorts; the
big divergences concentrate in datacenter geographies (US/SG crawler pools).

**Known limitation.** Some headless-Chrome pools pass *every* default heuristic —
real-looking UA, not on any datacenter list, `navigator.webdriver` spoofed to
`false`. Those still reach Mantecato and inflate **pageviews** (though the `/24`
collapse keeps them near one **visitor**). If pageview precision matters, extend
`DATACENTER_CIDRS`/bot rules, or filter obvious offenders (e.g. one key crawling
hundreds of unique paths in an hour) at read time.

**When reconciling with Umami specifically:** exclude its ingest-passed bots before
comparing, or a correct Mantecato number will read as a loss. The searchbot rows
live on the `session` table, so `JOIN session s … WHERE s.browser <> 'searchbot'`;
after that filter the residual pageview gap is the expected ~2–9 %/day GPC cohort.

## 5. How returning visitors are deduplicated (fixed monthly window)

The visitor digest salt rotates **once per calendar month** — a fixed,
non-configurable window chosen so the privacy posture cannot be misconfigured. A
returning visitor is therefore counted **once per month**:

- Within a month, the same person (same `/24` subnet + User-Agent) is one unique
  visitor, however many days they return.
- Over a range **longer than a month**, the per-month uniques are **summed** (no
  cross-month linkage), so "unique visitors" for a 6-month range is the sum of the
  six monthly figures, not a single 6-month dedup.

Precision trade-off: because the IP is always truncated to `/24` (+ `/48` for
IPv6) before hashing — the CNIL/Garante minimisation condition — distinct visitors
who share a `/24` subnet **and** an identical User-Agent in the same month merge
into one. This is the deliberate, fixed cost of needing no consent banner; see
[privacy.md](privacy.md). The **same** truncation is what collapses rotating-IP
bot pools into a single visitor key (§4), so on real deployments its net effect on
the visitor line is usually accuracy-positive, not negative.

## 6. Operational notes

- **Deploy propagation:** `/api/script` is served with `Cache-Control:
  max-age=86400`, so tracker changes take up to **24h** to fully roll out as
  browser caches expire. Lower it at your proxy if you need faster propagation.
- **Delivery reliability is already handled:** pageviews and engagement heartbeats
  are sent with `fetch(..., keepalive: true, credentials: "omit")`, so unload
  delivery stays reliable without sending existing first-party cookies to the
  collector.
- **Run the rollup** (`manage.py rollup_visitors`) daily for the retention
  guarantee; it does not affect live counts.
