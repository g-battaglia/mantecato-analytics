# Tracker

`packages/tracker/` — `@mantecato/tracker`. Lightweight JavaScript tracking script, wire-compatible with Umami's `/api/send` endpoint.

## Distribution

ESM + CommonJS + UMD builds via npm.

## Configuration

```typescript
interface TrackerConfig {
  websiteId: string              // Site UUID
  baseUrl: string                // Instance URL (no trailing slash)
  endpoint?: string              // API path override (default: /api/send)
  autoTrack?: boolean            // Auto-track pageviews (default: true)
  respectDNT?: boolean           // Respect Do-Not-Track (default: true)
  domains?: string[]             // Track only on these domains
  hostname?: string              // Custom hostname override
  tag?: string                   // Tracker instance identifier
  sessionReplay?: boolean        // Capture clicks/scroll (default: false)
  excludeSearch?: boolean        // Strip query string (default: false)
  excludeHash?: boolean          // Strip hash (default: false)
  beforeSend?: (type, payload) => payload | false
}
```

## Methods

```typescript
tracker.pageview(options?)                    // Track current URL
tracker.event(name, data?)                    // Custom event
tracker.revenue(amount, currency, data?)      // Revenue tracking
tracker.send(payload)                         // Raw payload
```

## Payload Format (Umami-compatible)

```typescript
{
  website: string       // Site UUID
  hostname: string      // Page hostname
  screen: string        // Screen resolution
  language: string      // Browser language
  title: string         // Page title
  url: string           // Page URL
  referrer: string      // Referrer URL
  name?: string         // Event name
  data?: object         // Event properties
  tag?: string          // Tracker tag
  revenue?: { amount: number, currency: string }
}
```

## Key Files

| File | Purpose |
|------|---------|
| `src/tracker.ts` | Main Tracker class |
| `src/script.ts` | Script tag auto-init (standalone `<script>` usage) |
| `src/index.ts` | ESM exports |
