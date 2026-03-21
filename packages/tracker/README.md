# @mantecato/tracker

Lightweight analytics tracker compatible with [Umami](https://umami.is). Sends pageviews and custom events to your Umami instance.

- **~2 KB** minified (IIFE script)
- Auto-tracks SPA route changes (pushState / popstate)
- Uses `sendBeacon` with `fetch` fallback
- Respects Do-Not-Track, skips bots and localhost
- ESM, CJS, and drop-in `<script>` tag builds

## Installation

### Script tag (easiest)

Add this to your HTML. Replace the `src` with your Mantecato instance URL and set your website ID:

```html
<script
  defer
  src="https://your-mantecato.com/api/script"
  data-website-id="your-website-uuid"
></script>
```

That's it — pageviews are tracked automatically, including SPA navigations.

#### Script attributes

| Attribute | Required | Default | Description |
|---|---|---|---|
| `data-website-id` | Yes | — | Your website UUID from Umami |
| `data-host-url` | No | Script origin | Umami API base URL |
| `data-domains` | No | Track all | Comma-separated list of allowed domains |
| `data-auto-track` | No | `true` | Auto-track pageviews on route changes |
| `data-respect-dnt` | No | `true` | Respect browser Do-Not-Track setting |
| `data-tag` | No | — | Tag to identify this tracker instance |

#### Manual events via script tag

The script exposes `window.mantecato` and `window.umami` globals:

```js
// Mantecato API
mantecato.event('signup', { plan: 'pro' });
mantecato.pageview();
mantecato.identify({ userId: '123' });

// Umami-compatible API
umami.track('signup', { plan: 'pro' });
umami.track(); // pageview
```

### npm package

```bash
npm install @mantecato/tracker
```

```ts
import { createTracker } from '@mantecato/tracker';

const tracker = createTracker({
  websiteId: 'your-website-uuid',
  baseUrl: 'https://your-mantecato.com',
});

// Pageviews are auto-tracked by default.
// Send custom events:
tracker.event('signup', { plan: 'pro' });
```

## API

### `createTracker(config): Tracker`

Creates a new tracker instance.

```ts
interface TrackerConfig {
  websiteId: string;        // Required — website UUID
  baseUrl: string;          // Required — Umami instance URL (no trailing slash)
  endpoint?: string;        // API path (default: "/api/send")
  autoTrack?: boolean;      // Auto-track pageviews (default: true)
  respectDNT?: boolean;     // Respect Do-Not-Track (default: true)
  domains?: string[];       // Only track on these domains
  hostname?: string;        // Override hostname sent to API
  tag?: string;             // Tag identifier
}
```

### Tracker methods

| Method | Description |
|---|---|
| `tracker.pageview(options?)` | Track a pageview. Options: `{ url, title, referrer }` |
| `tracker.event(name, data?)` | Track a custom event with optional key-value data |
| `tracker.identify(data)` | Identify the visitor with custom properties |
| `tracker.send(payload)` | Send a raw event payload (advanced) |
| `tracker.enable()` | Re-enable tracking after `disable()` |
| `tracker.disable()` | Temporarily disable tracking |
| `tracker.isEnabled()` | Check if tracking is active |
| `tracker.destroy()` | Remove all event listeners, stop auto-tracking |

## Frameworks

### Next.js (App Router)

```tsx
// app/layout.tsx
import Script from 'next/script';

export default function RootLayout({ children }) {
  return (
    <html>
      <body>
        {children}
        <Script
          defer
          src="https://your-mantecato.com/api/script"
          data-website-id="your-website-uuid"
        />
      </body>
    </html>
  );
}
```

### React (programmatic)

```tsx
import { useEffect, useRef } from 'react';
import { createTracker, type Tracker } from '@mantecato/tracker';

export function useTracker(websiteId: string, baseUrl: string) {
  const trackerRef = useRef<Tracker | null>(null);

  useEffect(() => {
    const tracker = createTracker({ websiteId, baseUrl });
    trackerRef.current = tracker;
    return () => tracker.destroy();
  }, [websiteId, baseUrl]);

  return trackerRef;
}
```

### Astro

```astro
<!-- src/layouts/Base.astro -->
<html>
  <body>
    <slot />
    <script
      defer
      src="https://your-mantecato.com/api/script"
      data-website-id="your-website-uuid"
    ></script>
  </body>
</html>
```

## Build

```bash
cd packages/tracker
npm run build
```

Outputs:
- `dist/index.js` — ESM
- `dist/index.cjs` — CommonJS
- `dist/index.d.ts` — TypeScript declarations
- `dist/script.js` — Minified IIFE for `<script>` tag

## License

MIT
