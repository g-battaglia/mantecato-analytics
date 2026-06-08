# @mantecato/tracker

Privacy-first tracking script for Mantecato Analytics. It sends anonymous
pageviews and named custom events to `/api/send` using the Umami-compatible
`type: "event"` envelope.

Collected payload fields are limited to:

- `website`
- `hostname`
- `url`
- `title`
- `name` for custom events
- `tag` when configured

The tracker does not send cookies, persistent identifiers, referrers, UTM
parameters, screen size, language, event properties, identify payloads,
revenue data, or session replay data.

## Installation

### Script Tag

```html
<script
  defer
  src="https://your-instance.com/api/script"
  data-website-id="your-website-uuid"
></script>
```

Pageviews are tracked automatically, including SPA route changes.

### Script Attributes

| Attribute | Required | Default | Description |
|---|---|---|---|
| `data-website-id` | Yes | - | Website UUID |
| `data-host-url` | No | Script origin | API base URL |
| `data-domains` | No | Track all | Comma-separated allowlist of domains |
| `data-auto-track` | No | `true` | Track pageviews on route changes |
| `data-respect-gpc` | No | `true` | Respect Global Privacy Control (GPC) — legally-recognised opt-out |
| `data-do-not-track` | No | `false` | Respect the legacy Do Not Track header (not legally binding) |
| `data-tag` | No | - | Deployment tag |

### HTML Events

```html
<button data-umami-event="signup">Sign up</button>
```

Only the event name is sent. `data-umami-event-*` property attributes are
ignored by design.

### Global API

The script exposes `window.mantecato` and `window.umami`:

```js
mantecato.pageview();
mantecato.event('signup');

umami.track();
umami.track('signup');
```

## npm

```bash
npm install @mantecato/tracker
```

```ts
import { createTracker } from '@mantecato/tracker';

const tracker = createTracker({
  websiteId: 'your-website-uuid',
  baseUrl: 'https://your-instance.com',
});

tracker.pageview();
tracker.event('signup');
```

## API

### `createTracker(config): Tracker`

```ts
interface TrackerConfig {
  websiteId: string;
  baseUrl: string;
  endpoint?: string;
  autoTrack?: boolean;
  respectDNT?: boolean;   // default false — legacy DNT is not legally binding
  respectGPC?: boolean;   // default true — GPC is a recognised opt-out signal
  domains?: string[];
  hostname?: string;
  tag?: string;
  excludeSearch?: boolean;
  excludeHash?: boolean;
  beforeSend?: (type: string, payload: UmamiPayload) => UmamiPayload | false | null | undefined;
  credentials?: RequestCredentials;
}
```

### Methods

| Method | Description |
|---|---|
| `tracker.pageview(options?)` | Track a pageview. Options: `{ url, title }` |
| `tracker.event(name, options?)` | Track a custom event name. Options: `{ url, title }` |
| `tracker.track()` | Umami-compatible pageview |
| `tracker.track(name)` | Umami-compatible custom event name |
| `tracker.track(payload)` | Sends only allowed fields from the payload |
| `tracker.enable()` / `tracker.disable()` | Toggle in-memory tracking |
| `tracker.isEnabled()` | Check current in-memory tracking state |
| `tracker.destroy()` | Remove listeners and stop auto-tracking |

## Frameworks

### Next.js App Router

```tsx
import Script from 'next/script';

export default function RootLayout({ children }) {
  return (
    <html>
      <body>
        {children}
        <Script
          defer
          src="https://your-instance.com/api/script"
          data-website-id="your-website-uuid"
        />
      </body>
    </html>
  );
}
```

### React

Use the companion package [`@mantecato/tracker-react`](../tracker-react):

```tsx
import { TrackerProvider, useTracker, usePageview } from '@mantecato/tracker-react';

function App() {
  return (
    <TrackerProvider websiteId="..." baseUrl="https://your-instance.com">
      <Page />
    </TrackerProvider>
  );
}

function Page() {
  usePageview();
  const { event } = useTracker();
  return <button onClick={() => event('cta_click')}>CTA</button>;
}
```

## Umami Compatibility

Mantecato accepts the Umami `type: "event"` envelope for pageviews and named
custom events. Unsupported Umami fields are dropped before sending or ignored
by the server.

## Build

```bash
cd packages/tracker
npm run build
```

## Test

```bash
npm test
```

## License

MIT
