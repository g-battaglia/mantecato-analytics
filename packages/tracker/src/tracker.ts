/**
 * @mantecato/tracker
 *
 * Analytics tracking script for Mantecato.
 * Wire-compatible with the Umami /api/send endpoint.
 *
 * Usage (npm):
 *   import { createTracker } from '@mantecato/tracker';
 *   const tracker = createTracker({ websiteId: '...', baseUrl: 'https://your-instance.com' });
 *   tracker.pageview();
 *   tracker.event('signup', { plan: 'pro' });
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
  /** Enable session replay data collection — click coordinates, scroll depth (default: false) */
  sessionReplay?: boolean;
  /** Strip query string from tracked URLs (default: false) */
  excludeSearch?: boolean;
  /** Strip hash from tracked URLs (default: false) */
  excludeHash?: boolean;
  /** Callback invoked before each send — return modified payload or falsy to cancel */
  beforeSend?: (type: string, payload: UmamiPayload) => UmamiPayload | false | null | undefined | Promise<UmamiPayload | false | null | undefined>;
  /** Fetch credentials mode (default: "omit") */
  credentials?: RequestCredentials;
}

export interface RevenueData {
  /** Revenue amount */
  amount: number;
  /** ISO 4217 currency code (e.g. "USD", "EUR") */
  currency: string;
}

export interface EventPayload {
  /** Custom event name */
  name?: string;
  /** Custom event data (key-value pairs) */
  data?: Record<string, string | number | boolean>;
  /** Override page URL */
  url?: string;
  /** Override page title */
  title?: string;
  /** Override referrer */
  referrer?: string;
  /** Revenue data for this event */
  revenue?: RevenueData;
}

export interface UmamiPayload {
  website: string;
  hostname: string;
  screen: string;
  language: string;
  title: string;
  url: string;
  referrer: string;
  name?: string;
  data?: Record<string, string | number | boolean>;
  tag?: string;
  revenue?: RevenueData;
  id?: string;
}

interface SendBody {
  type: "event" | "identify";
  payload: UmamiPayload;
}

/** Function that receives default payload and returns a modified payload */
export type TrackCallback = (props: UmamiPayload) => UmamiPayload;

export interface Tracker {
  /** Track a pageview for the current URL (or override with options) */
  pageview: (options?: Pick<EventPayload, "url" | "title" | "referrer">) => Promise<void>;
  /** Track a custom event */
  event: (name: string, data?: Record<string, string | number | boolean>) => Promise<void>;
  /** Track a revenue event */
  revenue: (amount: number, currency: string, data?: Record<string, string | number | boolean>) => Promise<void>;
  /** Send a raw payload (advanced) */
  send: (payload: EventPayload) => Promise<void>;
  /** Umami-compatible track() — overloaded: no args = pageview, string = event, object = raw payload, function = callback */
  track: {
    (): Promise<void>;
    (name: string, data?: Record<string, string | number | boolean>): Promise<void>;
    (payload: Partial<UmamiPayload>): Promise<void>;
    (callback: TrackCallback): Promise<void>;
  };
  /** Identify the current visitor — accepts data object or (id, data) like Umami */
  identify: {
    (data: Record<string, string | number | boolean>): Promise<void>;
    (id: string, data?: Record<string, string | number | boolean>): Promise<void>;
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

function getScreen(): string {
  if (typeof screen === "undefined") return "";
  return `${screen.width}x${screen.height}`;
}

function getLanguage(): string {
  if (typeof navigator === "undefined") return "";
  return navigator.language || "";
}

function getHostname(): string {
  if (typeof location === "undefined") return "";
  return location.hostname;
}

function getUrl(): string {
  if (typeof location === "undefined") return "";
  return location.pathname + location.search + (location.hash || "");
}

function getReferrer(): string {
  if (typeof document === "undefined") return "";
  return document.referrer;
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

function isLocalhost(): boolean {
  if (typeof location === "undefined") return false;
  return (
    location.hostname === "localhost" ||
    location.hostname === "127.0.0.1" ||
    location.hostname === "::1"
  );
}

function isDisabledByUser(): boolean {
  try {
    return (
      localStorage.getItem("mantecato.disabled") === "1" ||
      localStorage.getItem("umami.disabled") === "1"
    );
  } catch {
    return false;
  }
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
    sessionReplay = false,
    excludeSearch = false,
    excludeHash = false,
    beforeSend,
    credentials = "omit",
  } = config;

  let enabled = true;
  let disabled = false; // server-side disable flag
  let currentUrl = "";
  let currentReferrer = "";
  let cache = ""; // session token from server (x-umami-cache)
  let identity = ""; // persistent visitor ID from identify()
  let cleanupFns: Array<() => void> = [];

  /** Normalize a URL — strip search/hash per config, return full absolute URL like Umami */
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
    if (disabled) return false;
    if (!websiteId) return false;
    if (typeof window === "undefined") return false;
    if (isBot()) return false;
    if (respectDNT && isDNT()) return false;
    if (isLocalhost()) return false;
    if (isDisabledByUser()) return false;
    if (domains && domains.length > 0) {
      const host = getHostname();
      if (!domains.includes(host)) return false;
    }
    return true;
  }

  function buildPayload(eventPayload: EventPayload = {}): UmamiPayload {
    const url = normalize(eventPayload.url || getUrl());
    const referrer = eventPayload.referrer || currentReferrer || getReferrer();
    const title = eventPayload.title || getTitle();

    return {
      website: websiteId,
      hostname: customHostname || getHostname(),
      screen: getScreen(),
      language: getLanguage(),
      title,
      url,
      referrer,
      ...(eventPayload.name ? { name: eventPayload.name } : {}),
      ...(eventPayload.data ? { data: eventPayload.data } : {}),
      ...(eventPayload.revenue ? { revenue: eventPayload.revenue } : {}),
      ...(tag ? { tag } : {}),
      ...(identity ? { id: identity } : {}),
    };
  }

  // Send via fetch (primary) — reads response for cache token and disabled flag
  async function send(payload: UmamiPayload, type: "event" | "identify" = "event"): Promise<void> {
    if (!shouldTrack()) return;

    // beforeSend hook — can modify payload or cancel by returning falsy
    let finalPayload: UmamiPayload | false | null | undefined = payload;
    if (beforeSend) {
      finalPayload = await Promise.resolve(beforeSend(type, payload));
      if (!finalPayload) return;
    }

    const apiUrl = `${baseUrl}${endpoint}`;
    const body: SendBody = { type, payload: finalPayload };
    const jsonBody = JSON.stringify(body);

    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (cache) {
      headers["x-umami-cache"] = cache;
    }

    try {
      const res = await fetch(apiUrl, {
        method: "POST",
        headers,
        body: jsonBody,
        keepalive: true,
        credentials,
      });
      const data = await res.json();
      if (data) {
        if (data.cache) cache = data.cache;
        if (data.disabled) disabled = true;
      }
    } catch {
      // Silently ignore tracking failures
    }
  }

  /** Get the origin for same-origin referrer stripping */
  function getOrigin(): string {
    if (typeof location === "undefined") return "";
    return location.origin || "";
  }

  // Handle pushState/replaceState URL argument — matches Umami's handlePush
  function handlePush(_state: unknown, _title: unknown, url?: string | URL | null): void {
    if (!url) return;
    const newUrl = normalize(new URL(String(url), typeof location !== "undefined" ? location.href : undefined).toString());
    if (newUrl !== currentUrl) {
      currentReferrer = currentUrl;
      currentUrl = newUrl;
      setTimeout(() => send(buildPayload()), SPA_DELAY);
    }
  }

  // Set up auto-tracking
  function setupAutoTrack(): void {
    if (typeof window === "undefined") return;
    if (!autoTrack) return;

    currentUrl = normalize(typeof location !== "undefined" ? location.href : "");
    // Strip same-origin referrer, matching Umami behavior
    const ref = getReferrer();
    currentReferrer = normalize(ref.startsWith(getOrigin()) ? "" : ref);

    // Track initial pageview
    send(buildPayload());

    // Hook pushState/replaceState — callback fires BEFORE original, matching Umami
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
      // popstate doesn't provide URL arg — read from location after delay
      setTimeout(() => {
        const newUrl = normalize(typeof location !== "undefined" ? location.href : "");
        if (newUrl !== currentUrl) {
          currentReferrer = currentUrl;
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

  // Session replay: collect click coordinates and scroll depth
  function setupSessionReplay(): void {
    if (typeof window === "undefined" || typeof document === "undefined") return;
    if (!sessionReplay) return;

    const onClick = (e: MouseEvent) => {
      if (!shouldTrack()) return;
      const target = e.target as HTMLElement | null;
      const selector = target?.tagName?.toLowerCase() || "unknown";
      send(buildPayload({
        name: "_replay_click",
        data: {
          x: e.clientX,
          y: e.clientY,
          target: selector,
          ...(target?.id ? { id: target.id } : {}),
        },
      }));
    };

    let scrollTimer: ReturnType<typeof setTimeout> | null = null;
    const onScroll = () => {
      if (!shouldTrack()) return;
      if (scrollTimer) clearTimeout(scrollTimer);
      scrollTimer = setTimeout(() => {
        const scrollTop = window.scrollY || document.documentElement.scrollTop;
        const docHeight = Math.max(
          document.body.scrollHeight,
          document.documentElement.scrollHeight,
        );
        const winHeight = window.innerHeight;
        const depth = docHeight > winHeight
          ? Math.round((scrollTop / (docHeight - winHeight)) * 100)
          : 100;
        send(buildPayload({
          name: "_replay_scroll",
          data: { depth, scrollTop: Math.round(scrollTop) },
        }));
      }, 300);
    };

    document.addEventListener("click", onClick);
    window.addEventListener("scroll", onScroll, { passive: true });

    cleanupFns.push(() => {
      document.removeEventListener("click", onClick);
      window.removeEventListener("scroll", onScroll);
      if (scrollTimer) clearTimeout(scrollTimer);
    });
  }

  let initialized = false;

  function init(): void {
    if (initialized) return;
    initialized = true;
    setupAutoTrack();
    if (sessionReplay) setupSessionReplay();
  }

  // Initialize auto-tracking — use readystatechange like Umami, check shouldTrack before setup
  if (autoTrack && shouldTrack()) {
    if (typeof document !== "undefined" && document.readyState === "complete") {
      init();
    } else if (typeof document !== "undefined") {
      document.addEventListener("readystatechange", init, true);
      cleanupFns.push(() => document.removeEventListener("readystatechange", init, true));
    }
  }

  // Public API
  return {
    pageview(options) {
      const url = normalize(options?.url || getUrl());
      currentReferrer = currentUrl || getReferrer();
      currentUrl = url;
      return send(buildPayload({
        url,
        title: options?.title,
        referrer: options?.referrer || currentReferrer,
      }));
    },

    event(name, data) {
      return send(buildPayload({ name, data }));
    },

    revenue(amount, currency, data) {
      return send(buildPayload({
        name: "revenue",
        data: data || {},
        revenue: { amount, currency },
      }));
    },

    send(payload) {
      return send(buildPayload(payload));
    },

    track(nameOrPayloadOrFn?: string | Partial<UmamiPayload> | TrackCallback, data?: Record<string, string | number | boolean>) {
      if (typeof nameOrPayloadOrFn === "string") {
        return send(buildPayload({ name: nameOrPayloadOrFn, data }));
      } else if (typeof nameOrPayloadOrFn === "function") {
        return send(nameOrPayloadOrFn(buildPayload()));
      } else if (typeof nameOrPayloadOrFn === "object") {
        // Umami sends raw object only, no defaults merged
        return send({ ...nameOrPayloadOrFn } as UmamiPayload);
      } else {
        return send(buildPayload());
      }
    },

    identify(idOrData: string | Record<string, string | number | boolean>, data?: Record<string, string | number | boolean>) {
      if (typeof idOrData === "string") {
        identity = idOrData;
        cache = "";
        return send(
          buildPayload({ data: data ?? undefined }),
          "identify",
        );
      } else {
        cache = "";
        return send(
          buildPayload({ data: idOrData }),
          "identify",
        );
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
