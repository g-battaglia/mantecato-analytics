# @mantecato/tracker

Tracking script per Mantecato Analytics. Raccoglie pageview ed eventi personalizzati e li invia all'endpoint `/api/send`, wire-compatible con il protocollo Umami.

- **~2 KB** minified (IIFE script)
- Auto-tracks SPA route changes (pushState / popstate) con delay 300ms
- Revenue tracking (`tracker.revenue(amount, currency)`)
- Optional session replay data (click coordinates, scroll depth)
- Sessioni persistenti via `x-umami-cache` header
- `identify(id, data)` con `type: "identify"` (compatibile Umami)
- `data-umami-event` click tracking su elementi HTML
- `credentials: "omit"` e `keepalive: true` su fetch
- Rispetta Do-Not-Track (`window.doNotTrack`, `navigator.doNotTrack`, `navigator.msDoNotTrack`, GPC)
- Supporta `localStorage.getItem("umami.disabled")` per opt-out utente
- Filtra bot e localhost
- ESM, CJS, e drop-in `<script>` tag builds

## Installation

### Script tag

```html
<script
  defer
  src="https://your-instance.com/api/script"
  data-website-id="your-website-uuid"
></script>
```

Pageviews tracked automaticamente, incluse le navigazioni SPA.

#### Attributi script

| Attributo | Required | Default | Descrizione |
|---|---|---|---|
| `data-website-id` | Si | — | Website UUID |
| `data-host-url` | No | Script origin | Base URL dell'API |
| `data-domains` | No | Track all | Comma-separated list of allowed domains |
| `data-auto-track` | No | `true` | Auto-track pageview su route change |
| `data-respect-dnt` | No | `true` | Rispetta il Do-Not-Track del browser |
| `data-tag` | No | — | Tag per identificare questa istanza |

#### Eventi via attributi HTML (compatibile Umami)

```html
<button data-umami-event="signup" data-umami-event-plan="pro">Sign up</button>
```

Il click genera automaticamente l'evento `signup` con `{ plan: "pro" }`.

#### API globale

Lo script espone `window.mantecato` e `window.umami`:

```js
mantecato.event('signup', { plan: 'pro' });
mantecato.pageview();
mantecato.identify('user-42', { plan: 'enterprise' });

// Umami-compatible
umami.track('signup', { plan: 'pro' });
umami.track(); // pageview
umami.identify({ userId: '123' });
```

### npm

```bash
npm install @mantecato/tracker
```

```ts
import { createTracker } from '@mantecato/tracker';

const tracker = createTracker({
  websiteId: 'your-website-uuid',
  baseUrl: 'https://your-instance.com',
});

// Pageviews auto-tracked by default.
tracker.event('signup', { plan: 'pro' });
```

## API

### `createTracker(config): Tracker`

```ts
interface TrackerConfig {
  websiteId: string;        // Required — website UUID
  baseUrl: string;          // Required — instance URL (no trailing slash)
  endpoint?: string;        // API path (default: "/api/send")
  autoTrack?: boolean;      // Auto-track pageviews (default: true)
  respectDNT?: boolean;     // Respect Do-Not-Track (default: true)
  domains?: string[];       // Only track on these domains
  hostname?: string;        // Override hostname sent to API
  tag?: string;             // Tag identifier
  sessionReplay?: boolean;  // Collect click coords + scroll depth (default: false)
}
```

### Metodi

| Metodo | Descrizione |
|---|---|
| `tracker.pageview(options?)` | Track a pageview. Options: `{ url, title, referrer }` |
| `tracker.event(name, data?)` | Track a custom event |
| `tracker.revenue(amount, currency, data?)` | Track a revenue event |
| `tracker.identify(data)` | Identify con properties |
| `tracker.identify(id, data?)` | Identify con ID persistente (come Umami) |
| `tracker.send(payload)` | Send a raw event payload |
| `tracker.enable()` / `tracker.disable()` | Toggle tracking |
| `tracker.isEnabled()` | Check tracking status |
| `tracker.destroy()` | Rimuove listeners, stop auto-tracking |

### Revenue tracking

```ts
tracker.revenue(29.99, 'USD');
tracker.revenue(100, 'EUR', { product: 'widget', plan: 'pro' });
```

### Session replay

```ts
const tracker = createTracker({
  websiteId: '...',
  baseUrl: '...',
  sessionReplay: true, // sends _replay_click and _replay_scroll events
});
```

### Identify

```ts
// Con properties (come Umami con singolo argomento)
tracker.identify({ userId: '123', plan: 'pro' });

// Con ID persistente (come Umami con due argomenti)
tracker.identify('user-42', { plan: 'enterprise' });
// L'ID viene incluso in tutti i payload successivi
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
          src="https://your-instance.com/api/script"
          data-website-id="your-website-uuid"
        />
      </body>
    </html>
  );
}
```

### React

Usa il pacchetto companion [`@mantecato/tracker-react`](../tracker-react):

```bash
npm install @mantecato/tracker-react
```

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
      src="https://your-instance.com/api/script"
      data-website-id="your-website-uuid"
    ></script>
  </body>
</html>
```

## Compatibilita Umami

Il tracker e wire-compatible con Umami v2:

- Payload format identico (`{ type, payload }`)
- `type: "event"` per pageview/eventi, `type: "identify"` per identify
- Session tracking via `x-umami-cache` header (letto dalla risposta del server)
- `credentials: "omit"` su fetch (come Umami)
- Delay 300ms su SPA route change (come Umami)
- Supporta `localStorage.getItem("umami.disabled")` per opt-out
- `data-umami-event` / `data-umami-event-*` click tracking
- `identify(id, data)` con ID persistente e reset cache

Estensioni Mantecato (ignorati silenziosamente da un backend Umami stock):
- `revenue` field nel payload
- `_replay_click` / `_replay_scroll` eventi per session replay

## Build

```bash
cd packages/tracker
npm run build
```

Output:
- `dist/index.js` — ESM
- `dist/index.cjs` — CommonJS
- `dist/index.d.ts` — TypeScript declarations
- `dist/script.js` — Minified IIFE per `<script>` tag

## Test

```bash
npm test        # run once
npm run test:watch  # watch mode
```

## License

MIT
