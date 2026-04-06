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

interface UmamiPayload {
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

export interface Tracker {
  /** Track a pageview for the current URL (or override with options) */
  pageview: (options?: Pick<EventPayload, "url" | "title" | "referrer">) => void;
  /** Track a custom event */
  event: (name: string, data?: Record<string, string | number | boolean>) => void;
  /** Track a revenue event */
  revenue: (amount: number, currency: string, data?: Record<string, string | number | boolean>) => void;
  /** Send a raw payload (advanced) */
  send: (payload: EventPayload) => void;
  /** Identify the current visitor — accepts data object or (id, data) like Umami */
  identify: {
    (data: Record<string, string | number | boolean>): void;
    (id: string, data?: Record<string, string | number | boolean>): void;
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
  return location.pathname + location.search;
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
    return localStorage.getItem("umami.disabled") === "1";
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
  } = config;

  let enabled = true;
  let disabled = false; // server-side disable flag
  let currentUrl = "";
  let currentReferrer = "";
  let cache = ""; // session token from server (x-umami-cache)
  let identity = ""; // persistent visitor ID from identify()
  let cleanupFns: Array<() => void> = [];

  function shouldTrack(): boolean {
    if (!enabled) return false;
    if (disabled) return false;
    if (typeof window === "undefined") return false;
    if (isBot()) return false;
    if (respectDNT && isDNT()) return false;
    if (isLocalhost()) return false;
    if (isDisabledByUser()) return false;
    if (domains && domains.length > 0) {
      const host = getHostname();
      if (!domains.some((d) => host === d || host.endsWith(`.${d}`))) {
        return false;
      }
    }
    return true;
  }

  function buildPayload(eventPayload: EventPayload = {}): UmamiPayload {
    const url = eventPayload.url || getUrl();
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
  function send(payload: UmamiPayload, type: "event" | "identify" = "event"): void {
    if (!shouldTrack()) return;

    const apiUrl = `${baseUrl}${endpoint}`;
    const body: SendBody = { type, payload };
    const jsonBody = JSON.stringify(body);

    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (cache) {
      headers["x-umami-cache"] = cache;
    }

    fetch(apiUrl, {
      method: "POST",
      headers,
      body: jsonBody,
      keepalive: true,
      credentials: "omit",
    })
      .then((res) => res.json())
      .then((data) => {
        if (data) {
          if (data.cache) cache = data.cache;
          if (data.disabled) disabled = true;
        }
      })
      .catch(() => {
        // Silently ignore tracking failures
      });
  }

  // Handle route changes for SPAs
  function handleRouteChange(): void {
    const newUrl = getUrl();
    if (newUrl === currentUrl) return;
    currentReferrer = currentUrl;
    currentUrl = newUrl;
    send(buildPayload({ url: currentUrl, referrer: currentReferrer }));
  }

  // Set up auto-tracking
  function setupAutoTrack(): void {
    if (typeof window === "undefined") return;
    if (!autoTrack) return;

    currentUrl = getUrl();
    currentReferrer = getReferrer();

    // Track initial pageview
    send(buildPayload());

    // Listen for pushState / replaceState / popstate for SPA navigation
    const originalPushState = history.pushState;
    const originalReplaceState = history.replaceState;

    history.pushState = function (...args) {
      originalPushState.apply(this, args);
      setTimeout(handleRouteChange, SPA_DELAY);
    };

    history.replaceState = function (...args) {
      originalReplaceState.apply(this, args);
      setTimeout(handleRouteChange, SPA_DELAY);
    };

    const onPopState = () => {
      setTimeout(handleRouteChange, SPA_DELAY);
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

  // Initialize auto-tracking
  if (autoTrack) {
    if (typeof document !== "undefined" && document.readyState === "complete") {
      setupAutoTrack();
    } else if (typeof window !== "undefined") {
      const onLoad = () => {
        setupAutoTrack();
        window.removeEventListener("load", onLoad);
      };
      window.addEventListener("load", onLoad);
      cleanupFns.push(() => window.removeEventListener("load", onLoad));
    }
  }

  // Initialize session replay
  if (sessionReplay) {
    if (typeof document !== "undefined" && document.readyState === "complete") {
      setupSessionReplay();
    } else if (typeof window !== "undefined") {
      const onLoad = () => {
        setupSessionReplay();
        window.removeEventListener("load", onLoad);
      };
      window.addEventListener("load", onLoad);
      cleanupFns.push(() => window.removeEventListener("load", onLoad));
    }
  }

  // Public API
  return {
    pageview(options) {
      const url = options?.url || getUrl();
      currentReferrer = currentUrl || getReferrer();
      currentUrl = url;
      send(buildPayload({
        url,
        title: options?.title,
        referrer: options?.referrer || currentReferrer,
      }));
    },

    event(name, data) {
      send(buildPayload({ name, data }));
    },

    revenue(amount, currency, data) {
      send(buildPayload({
        name: "revenue",
        data: data || {},
        revenue: { amount, currency },
      }));
    },

    send(payload) {
      send(buildPayload(payload));
    },

    identify(idOrData: string | Record<string, string | number | boolean>, data?: Record<string, string | number | boolean>) {
      // Match Umami signature: identify(data) or identify(id, data)
      if (typeof idOrData === "string") {
        identity = idOrData;
        cache = ""; // clear cache to force re-identification, like Umami
        send(
          buildPayload({ data: data ?? undefined }),
          "identify",
        );
      } else {
        cache = "";
        send(
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
