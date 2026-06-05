# apps/tracker -- Event Ingestion System

This module is the data entry point for analytics. It receives pageviews and
custom events from the JavaScript tracker (`@mantecato/tracker`) via
`POST /api/send` and inserts them into the PostgreSQL database.

## What It Does

- Receives pageview and custom event data via an Umami-compatible wire protocol
- Resolves sessions and visits deterministically (no server-side storage)
- Performs IP geolocation (MaxMind + CDN header fallback)
- Parses the User-Agent to extract browser, OS, and device type
- Inserts data into the `website_event`, `event_data`, `session_data`, and `revenue` tables
- Serves the JavaScript tracker bundle via `GET /api/script`

## Wire Protocol

The protocol is compatible with Umami: the tracker sends `POST /api/send`
requests with a JSON body in two formats:

### Event (pageview or custom event)

```json
{
  "type": "event",
  "payload": {
    "website": "<uuid>",
    "url": "/page",
    "referrer": "https://google.com",
    "title": "Page Title",
    "hostname": "example.com",
    "screen": "1920x1080",
    "language": "it-IT",
    "name": "signup",
    "tag": "cta-hero",
    "data": {"plan": "pro", "value": 42},
    "revenue": {"amount": 29.99, "currency": "EUR"}
  }
}
```

- Without `name`: pageview (`event_type = 1`)
- With `name`: custom event (`event_type = 2`)
- `data`: arbitrary custom properties (max 50 keys, values truncated to 500 characters)
- `revenue`: optional revenue data for e-commerce

### Identify (user association)

```json
{
  "type": "identify",
  "payload": {
    "website": "<uuid>",
    "id": "user_42",
    "data": {"plan": "pro", "company": "Acme"}
  }
}
```

Associates a user identifier and custom properties with the current session.

### Response

```json
{"cache": "<signed_session_token>"}
```

The token is returned to the JS tracker to maintain session continuity
across subsequent requests.

## Architecture

```
views.py          HTTP endpoints: IngestView (POST /api/send), api_script (GET /api/script)
    |
    v
services.py       Business logic: ingest_event(), ingest_identify()
    |              URL, referrer, UTM, click ID parsing
    |              Inserts into website_event, event_data, revenue, session_data
    |
session.py        Session resolution: deterministic session_id and visit_id
    |              Signed token for client-side continuity
    |
geo.py            Geolocation: CDN headers + MaxMind GeoLite2-City
    |
ip.py             Real IP extraction from proxy/CDN header chain
    |
ua.py             User-Agent parsing: browser, OS, device type
```

## Data Flow

```
Browser/App                     Mantecato Server
-----------                     ----------------

tracker.js ----POST /api/send----> IngestView.post()
               (JSON body)              |
               + headers:               |-- get_client_ip(request)     [ip.py]
                 X-Mantecato-Session    |-- parse_user_agent(UA)       [ua.py]
                 User-Agent             |-- resolve_geo(request, ip)   [geo.py]
                                        |-- resolve_session(...)       [session.py]
                                        |
                                        |-- ingest_event()             [services.py]
                                        |     |-- INSERT website_event
                                        |     |-- INSERT event_data    (if payload.data)
                                        |     |-- INSERT revenue       (if payload.revenue)
                                        |
                                        |-- or ingest_identify()       [services.py]
                                        |     |-- UPDATE session.distinct_id
                                        |     |-- INSERT session_data
                                        |
               <---200 {"cache": token}-+
```

## Session Resolution

The `session.py` module implements a deterministic algorithm that avoids
server-side storage. Session and visit UUIDs are derived from known inputs:

### session_id Generation

```
session_id = UUID5(website_id + IP + User-Agent + monthly_salt)
```

- `monthly_salt` = SHA-512 of the first day of the current month (UTC)
- The same browser/IP within the same month produces the same `session_id`
- When the month changes, the session is regenerated

### visit_id Generation

```
visit_id = UUID5(session_id + hourly_salt)
```

- `hourly_salt` = SHA-512 of the start of the current hour (UTC)
- Within the same hour, the same session produces the same `visit_id`

### Two Resolution Paths

**Path A -- returning visitor (valid token in header):**

1. The signed token is decoded and verified
2. The `session_id` is reused from the token
3. If the gap since the last event exceeds 30 minutes, a new `visit_id` is generated
4. Otherwise the `visit_id` is reused

**Path B -- new visitor (no token or invalid token):**

1. `session_id` computed deterministically from the fingerprint
2. `visit_id` computed from `session_id` + hourly salt
3. Session row inserted with `ON CONFLICT DO NOTHING` (idempotent)

### Session Token

The token carries `session_id|visit_id|unix_timestamp`, signed with
`django.core.signing.Signer` (based on `SECRET_KEY`). The JS tracker
receives it in the `cache` field of the response and sends it back in the
`x-mantecato-session` header (or `x-umami-cache` for compatibility).

## GeoIP Resolution

The `geo.py` module uses a two-tier strategy:

### Tier 1: CDN Headers (preferred)

If the server is behind a CDN, geolocation headers are already available
in the request. They are checked in order of priority:

| CDN | Header country | Header region | Header city |
|---|---|---|---|
| Cloudflare | `CF-IPCountry` | `CF-Region-Code` | `CF-IPCity` |
| Vercel | `X-Vercel-IP-Country` | `X-Vercel-IP-Country-Region` | `X-Vercel-IP-City` |
| CloudFront | `CloudFront-Viewer-Country` | `CloudFront-Viewer-Country-Region` | `CloudFront-Viewer-City` |

### Tier 2: MaxMind GeoLite2-City (fallback)

If no CDN headers are present, a local lookup is performed against the
MaxMind GeoLite2-City database. The database can be downloaded with:

```bash
python manage.py downloadgeo
```

The `.mmdb` file path is configurable via the `GEOIP_PATH` environment variable.
Default: `<BASE_DIR>/geo/GeoLite2-City.mmdb`.

## IP Extraction

The `ip.py` module checks headers in the following order of priority:

1. **Custom header** -- configurable via `CLIENT_IP_HEADER` (env var)
2. **CDN/proxy headers** -- single headers set by the infrastructure:
   - `True-Client-IP` (Akamai, Cloudflare Enterprise)
   - `CF-Connecting-IP` (Cloudflare)
   - `Fastly-Client-IP` (Fastly)
   - `X-NF-Client-Connection-IP` (Netlify)
   - `DO-Connecting-IP` (DigitalOcean)
   - `X-Real-IP` (Nginx)
   - `X-AppEngine-User-IP` (Google App Engine)
   - `X-Cluster-Client-IP` (Rackspace)
3. **X-Forwarded-For** -- first IP (leftmost)
4. **Forwarded** (RFC 7239) -- `for=` directive
5. **X-Forwarded** -- non-standard variant
6. **X-Client-IP / REMOTE_ADDR** -- final fallback

Port suffixes are automatically stripped (both IPv4 and IPv6).

## User-Agent Parsing

The `ua.py` module uses the `ua-parser` library to extract:

- **browser**: browser family (Chrome, Safari, Firefox, ...)
- **os**: operating system (Windows, iOS, Android, ...)
- **device**: device type (`desktop`, `mobile`, `tablet`)

Values of `"Other"` are normalized to `None`. If `ua-parser` is not installed,
all fields are `None`. All values are truncated to 20 characters.

## CORS

The `POST /api/send` endpoint is a public write-only API: the JS tracker
runs on client domains, which differ from the Mantecato server. For this reason:

- `Access-Control-Allow-Origin: *` (intentional wildcard)
- `Access-Control-Allow-Headers: Content-Type, x-mantecato-session, x-umami-cache`
- The `OPTIONS` preflight has an `Access-Control-Max-Age` of 24 hours
- CSRF is disabled on this endpoint (`@csrf_exempt`)

## Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/send` | Event and identify ingestion |
| `OPTIONS` | `/api/send` | CORS preflight |
| `GET` | `/api/script` | JavaScript tracker bundle (cached in memory) |
