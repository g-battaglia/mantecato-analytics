/**
 * @mantecato/tracker
 *
 * Privacy-first analytics tracking script for Mantecato.
 * Collects only anonymous aggregate pageview data — no cookies, no identifiers,
 * no fingerprinting, no session tracking.
 *
 * Usage (npm):
 *   import { createTracker } from '@mantecato/tracker';
 *   const tracker = createTracker({ websiteId: '...', baseUrl: 'https://your-instance.com' });
 *   tracker.pageview();
 *
 * Usage (script tag):
 *   <script defer src="https://your-instance.com/api/script" data-website-id="..."></script>
 */

// --- Types ---

export interface TrackerConfig {
  /** The website UUID */
  websiteId: string;
  /** Base URL of your Mantecato / Umami instance (no trailing slash) */
  baseUrl: string;
  /** Override the API endpoint path (default: "/api/send") */
  endpoint?: string;
  /** Auto-track pageviews on route changes (default: true) */
  autoTrack?: boolean;
  /** Respect Do-Not-Track browser setting (default: true) */
  respectDNT?: boolean;
  /** Domains to track — if set, only track on these domains (default: track all) */
  domains?: string[];
  /** Custom hostname override */
  hostname?: string;
  /** Tag to identify this tracker instance */
  tag?: string;
  /** Strip query string from tracked URLs (default: false) */
  excludeSearch?: boolean;
  /** Strip hash from tracked URLs (default: false) */
  excludeHash?: boolean;
  /** Callback invoked before each send — return modified payload or falsy to cancel */
  beforeSend?: (type: string, payload: UmamiPayload) => UmamiPayload | false | null | undefined | Promise<UmamiPayload | false | null | undefined>;
  /** Fetch credentials mode (default: "omit") */
  credentials?: RequestCredentials;
}

export interface EventPayload {
  /** Override page URL */
  url?: string;
  /** Override page title */
  title?: string;
}

export interface UmamiPayload {
  website: string;
  hostname: string;
  title: string;
  url: string;
  /** Custom event name. Omitted for pageviews. */
  name?: string;
  tag?: string;
}

interface SendBody {
  type: "event";
  payload: UmamiPayload;
}

/** Function that receives default payload and returns a modified payload */
export type TrackCallback = (props: UmamiPayload) => UmamiPayload;

export interface Tracker {
  /** Track a pageview for the current URL (or override with options) */
  pageview: (options?: Pick<EventPayload, "url" | "title">) => Promise<void>;
  /** Track a custom event name without event properties */
  event: (name: string, options?: Pick<EventPayload, "url" | "title">) => Promise<void>;
  /** Umami-compatible track() — no args = pageview, string = event name, object/function = sanitized payload */
  track: {
    (): Promise<void>;
    (name: string): Promise<void>;
    (payload: Partial<UmamiPayload>): Promise<void>;
    (callback: TrackCallback): Promise<void>;
  };
  /** Enable tracking (if it was disabled) */
  enable: () => void;
  /** Disable tracking */
  disable: () => void;
  /** Check if tracking is enabled */
  isEnabled: () => boolean;
  /** Destroy the tracker — removes event listeners and stops auto-tracking */
  destroy: () => void;
}

// --- Helpers ---

function getHostname(): string {
  if (typeof location === "undefined") return "";
  return location.hostname;
}

function getUrl(): string {
  if (typeof location === "undefined") return "";
  return location.pathname + location.search + (location.hash || "");
}

function getTitle(): string {
  if (typeof document === "undefined") return "";
  return document.title;
}

function isDNT(): boolean {
  const w = typeof window !== "undefined" ? (window as unknown as Record<string, unknown>) : {};
  const n = typeof navigator !== "undefined" ? (navigator as unknown as Record<string, unknown>) : {};
  const dnt = w.doNotTrack || n.doNotTrack || n.msDoNotTrack || n.globalPrivacyControl;
  return dnt === 1 || dnt === "1" || dnt === "yes" || dnt === true;
}

function isBot(): boolean {
  if (typeof navigator === "undefined") return false;
  return /bot|crawl|spider|slurp|lighthouse/i.test(navigator.userAgent);
}

// --- Core ---

const SPA_DELAY = 300;

export function createTracker(config: TrackerConfig): Tracker {
  const {
    websiteId,
    baseUrl,
    endpoint = "/api/send",
    autoTrack = true,
    respectDNT = true,
    domains,
    hostname: customHostname,
    tag,
    excludeSearch = false,
    excludeHash = false,
    beforeSend,
    credentials = "omit",
  } = config;

  let enabled = true;
  let currentUrl = "";
  let cleanupFns: Array<() => void> = [];

  function normalize(raw: string): string {
    if (!raw) return raw;
    try {
      const u = new URL(raw, typeof location !== "undefined" ? location.href : undefined);
      if (excludeSearch) u.search = "";
      if (excludeHash) u.hash = "";
      return u.toString();
    } catch {
      return raw;
    }
  }

  function shouldTrack(): boolean {
    if (!enabled) return false;
    if (!websiteId) return false;
    if (typeof window === "undefined") return false;
    if (isBot()) return false;
    if (respectDNT && isDNT()) return false;
    if (domains && domains.length > 0) {
      const host = getHostname();
      if (!domains.includes(host)) return false;
    }
    return true;
  }

  function buildPayload(eventPayload: EventPayload = {}): UmamiPayload {
    const url = normalize(eventPayload.url || getUrl());
    const title = eventPayload.title || getTitle();

    return {
      website: websiteId,
      hostname: customHostname || getHostname(),
      title,
      url,
      ...(tag ? { tag } : {}),
    };
  }

  function sanitizePayload(payload: Partial<UmamiPayload>): UmamiPayload {
    const base = buildPayload({
      url: payload.url,
      title: payload.title,
    });
    const name = typeof payload.name === "string" ? payload.name.trim().slice(0, 100) : "";
    return {
      ...base,
      hostname: payload.hostname || base.hostname,
      ...(name ? { name } : {}),
      ...(tag ? { tag } : {}),
    };
  }

  async function send(payload: UmamiPayload): Promise<void> {
    if (!shouldTrack()) return;

    let finalPayload: UmamiPayload | false | null | undefined = payload;
    if (beforeSend) {
      finalPayload = await Promise.resolve(beforeSend("event", payload));
      if (!finalPayload) return;
    }

    const apiUrl = `${baseUrl}${endpoint}`;
    const body: SendBody = { type: "event", payload: sanitizePayload(finalPayload) };

    try {
      await fetch(apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        keepalive: true,
        credentials,
      });
    } catch {
      // Silently ignore tracking failures
    }
  }

  function handlePush(_state: unknown, _title: unknown, url?: string | URL | null): void {
    if (!url) return;
    const newUrl = normalize(new URL(String(url), typeof location !== "undefined" ? location.href : undefined).toString());
    if (newUrl !== currentUrl) {
      currentUrl = newUrl;
      setTimeout(() => send(buildPayload()), SPA_DELAY);
    }
  }

  function setupAutoTrack(): void {
    if (typeof window === "undefined") return;
    if (!autoTrack) return;

    currentUrl = normalize(typeof location !== "undefined" ? location.href : "");

    send(buildPayload());

    const originalPushState = history.pushState;
    const originalReplaceState = history.replaceState;

    history.pushState = function (...args: Parameters<typeof originalPushState>) {
      handlePush(args[0], args[1], args[2]);
      return originalPushState.apply(this, args);
    };

    history.replaceState = function (...args: Parameters<typeof originalReplaceState>) {
      handlePush(args[0], args[1], args[2]);
      return originalReplaceState.apply(this, args);
    };

    const onPopState = () => {
      setTimeout(() => {
        const newUrl = normalize(typeof location !== "undefined" ? location.href : "");
        if (newUrl !== currentUrl) {
          currentUrl = newUrl;
          send(buildPayload());
        }
      }, SPA_DELAY);
    };
    window.addEventListener("popstate", onPopState);

    cleanupFns.push(() => {
      history.pushState = originalPushState;
      history.replaceState = originalReplaceState;
      window.removeEventListener("popstate", onPopState);
    });
  }

  let initialized = false;

  function init(): void {
    if (initialized) return;
    initialized = true;
    setupAutoTrack();
  }

  if (autoTrack && shouldTrack()) {
    if (typeof document !== "undefined" && document.readyState === "complete") {
      init();
    } else if (typeof document !== "undefined") {
      document.addEventListener("readystatechange", init, true);
      cleanupFns.push(() => document.removeEventListener("readystatechange", init, true));
    }
  }

  return {
    pageview(options) {
      const url = normalize(options?.url || getUrl());
      currentUrl = url;
      return send(buildPayload({ url, title: options?.title }));
    },

    event(name, options) {
      const url = normalize(options?.url || getUrl());
      currentUrl = url;
      return send({ ...buildPayload({ url, title: options?.title }), name });
    },

    track(payloadOrFn?: string | Partial<UmamiPayload> | TrackCallback) {
      if (typeof payloadOrFn === "function") {
        return send(payloadOrFn(buildPayload()));
      } else if (typeof payloadOrFn === "string") {
        return send({ ...buildPayload(), name: payloadOrFn });
      } else if (typeof payloadOrFn === "object") {
        return send(sanitizePayload(payloadOrFn));
      } else {
        return send(buildPayload());
      }
    },

    enable() {
      enabled = true;
    },

    disable() {
      enabled = false;
    },

    isEnabled() {
      return enabled;
    },

    destroy() {
      enabled = false;
      for (const fn of cleanupFns) {
        try { fn(); } catch { /* ignore */ }
      }
      cleanupFns = [];
    },
  };
}
