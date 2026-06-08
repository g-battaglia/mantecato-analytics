# @mantecato/tracker-react

React hooks e provider per [`@mantecato/tracker`](../tracker). Analytics drop-in per qualsiasi app React.

## Installation

```bash
npm install @mantecato/tracker-react
```

Peer dependency: `react >= 18`.

## Quick start

```tsx
import { TrackerProvider, useTracker, usePageview } from '@mantecato/tracker-react';

function App() {
  return (
    <TrackerProvider websiteId="your-website-uuid" baseUrl="https://your-mantecato.com">
      <Router />
    </TrackerProvider>
  );
}
```

## API

### `<TrackerProvider>`

Wraps your app and creates a single tracker instance. Accepts all [`TrackerConfig`](../tracker/README.md#createtrackerconfig-tracker) props plus `children`.

```tsx
<TrackerProvider
  websiteId="..."
  baseUrl="https://your-mantecato.com"
  autoTrack={true}          // default
  respectDNT={true}         // default
  tag="production"
>
  {children}
</TrackerProvider>
```

The tracker is created once and destroyed on unmount. It only recreates if `websiteId` or `baseUrl` change.

### `useTracker()`

Returns the `Tracker` instance from the nearest `TrackerProvider`. Throws if used outside a provider.

```tsx
function SignupButton() {
  const { event } = useTracker();

  const handleClick = () => {
    event('signup');
  };

  return <button onClick={handleClick}>Sign up</button>;
}
```

Available tracker methods are: `pageview`, `event`, `track`, `enable`, `disable`, `isEnabled`, `destroy`.

### `usePageview(url?, title?)`

Tracks a pageview when the component mounts. Deduplicates by URL so remounts don't double-count.

```tsx
// Auto-detect URL from window.location
function Page() {
  usePageview();
  return <div>...</div>;
}

// Explicit URL (useful for dynamic routes)
function ProductPage({ slug }: { slug: string }) {
  usePageview(`/products/${slug}`);
  return <div>Product: {slug}</div>;
}

// With custom title
function BlogPost({ post }: { post: Post }) {
  usePageview(`/blog/${post.slug}`, post.title);
  return <article>...</article>;
}
```

## With React Router

```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { TrackerProvider } from '@mantecato/tracker-react';

function App() {
  return (
    <TrackerProvider websiteId="..." baseUrl="..." autoTrack={true}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/about" element={<About />} />
        </Routes>
      </BrowserRouter>
    </TrackerProvider>
  );
}
```

With `autoTrack: true` (default), route changes are tracked automatically via the SPA router integration in `@mantecato/tracker`. No need to call `usePageview` on every page unless you want custom URLs or titles.

## Build

```bash
cd packages/tracker-react
npm run build
```

## License

MIT
