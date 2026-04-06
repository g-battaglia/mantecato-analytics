# @mantecato/tracker

Lightweight analytics tracker compatible with [Umami](https://umami.is). Sends pageviews and custom events to your Umami instance.

- **~2 KB** minified (IIFE script)
- Auto-tracks SPA route changes (pushState / popstate)
- Revenue tracking (`tracker.revenue(amount, currency)`)
- Optional session replay data (click coordinates, scroll depth)
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
  sessionReplay?: boolean;  // Collect click coords + scroll depth (default: false)
}
```

### Tracker methods

| Method | Description |
|---|---|
| `tracker.pageview(options?)` | Track a pageview. Options: `{ url, title, referrer }` |
| `tracker.event(name, data?)` | Track a custom event with optional key-value data |
| `tracker.revenue(amount, currency, data?)` | Track a revenue event |
| `tracker.identify(data)` | Identify the visitor with custom properties |
| `tracker.send(payload)` | Send a raw event payload (advanced) |
| `tracker.enable()` | Re-enable tracking after `disable()` |
| `tracker.disable()` | Temporarily disable tracking |
| `tracker.isEnabled()` | Check if tracking is active |
| `tracker.destroy()` | Remove all event listeners, stop auto-tracking |

### Revenue tracking

```ts
// Track a purchase
tracker.revenue(29.99, 'USD');

// With additional data
tracker.revenue(100, 'EUR', { product: 'widget', plan: 'pro' });
```

### Session replay

Enable optional collection of click coordinates and scroll depth:

```ts
const tracker = createTracker({
  websiteId: '...',
  baseUrl: '...',
  sessionReplay: true, // sends _replay_click and _replay_scroll events
});
```

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

### React

Use the companion [`@mantecato/tracker-react`](../tracker-react) package for a ready-made provider and hooks:

```bash
npm install @mantecato/tracker-react
```

```tsx
import { TrackerProvider, useTracker, usePageview } from '@mantecato/tracker-react';

function App() {
  return (
    <TrackerProvider websiteId="..." baseUrl="https://your-mantecato.com">
      <Page />
    </TrackerProvider>
  );
}

function Page() {
  usePageview(); // auto-tracks on mount
  const { event, revenue } = useTracker();
  return <button onClick={() => event('click', { target: 'cta' })}>CTA</button>;
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
