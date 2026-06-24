# apps/tracker -- Event Ingestion

This module receives anonymous analytics events from `@mantecato/tracker` via
`POST /api/send` and writes aggregate-safe rows to `website_event`.

## What It Stores

- Pageviews (`event_type = 1`)
- Custom events by name only (`event_type = 2`)
- URL path only (query string and fragment discarded), page title, hostname
- Coarse browser, OS, and device labels parsed from the User-Agent
- Country code
- Event-level bot flag and bot reason

It does not store sessions, visit IDs, raw IPs, raw User-Agents, query strings,
URL fragments, UTM parameters, click IDs, screen size, language, event
payload/properties, identify data, or revenue data. Referrers are reduced to the
bare referring domain.

## Wire Protocol

The endpoint accepts the Umami-compatible `type: "event"` envelope.

### Pageview

```json
{
  "type": "event",
  "payload": {
    "website": "<uuid>",
    "url": "/page",
    "title": "Page Title",
    "hostname": "example.com"
  }
}
```

### Custom Event

```json
{
  "type": "event",
  "payload": {
    "website": "<uuid>",
    "url": "/page",
    "title": "Page Title",
    "hostname": "example.com",
    "name": "signup"
  }
}
```

Only `name` is accepted for custom events. Any submitted properties are ignored.

### Response

```json
{}
```

No session cache token is returned.

## Visitor Counts

During ingestion, the server derives a window-scoped HMAC digest from request
attributes already present in the HTTP request. Raw IPs and raw User-Agents are
never stored; the digest is nulled after retention and the window salt is
discarded at window end.

## Architecture

```text
views.py       HTTP endpoint: IngestView (POST /api/send), api_script (GET /api/script)
services.py    Writes WebsiteEvent rows and updates aggregate visitor sketches
ip.py          Real IP extraction from proxy/CDN header chain
geo.py         Country resolution from MaxMind and CDN headers
ua.py          Coarse User-Agent parsing and bot classification
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/send` | Pageview/custom-event ingestion |
| `GET` | `/api/script` | JavaScript tracker bundle |
