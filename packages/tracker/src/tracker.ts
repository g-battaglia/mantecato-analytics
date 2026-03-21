/**
 * @mantecato/tracker
 *
 * Lightweight analytics tracker compatible with Umami.
 * Sends pageviews and custom events to your Umami instance.
 *
 * Usage (npm):
 *   import { createTracker } from '@mantecato/tracker';
 *   const tracker = createTracker({ websiteId: '...', baseUrl: 'https://your-umami.com' });
 *   tracker.pageview();
 *   tracker.event('signup', { plan: 'pro' });
 *
 * Usage (script tag):
 *   <script defer src="https://your-umami.com/script.js" data-website-id="..."></script>
 */

// --- Types ---

export interface TrackerConfig {
  /** The website UUID from Umami */
  websiteId: string;
  /** Base URL of your Umami instance (no trailing slash) */
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
}

interface SendBody {
  type: "event";
  payload: UmamiPayload;
}

export interface Tracker {
  /** Track a pageview for the current URL (or override with options) */
  pageview: (options?: Pick<EventPayload, "url" | "title" | "referrer">) => void;
  /** Track a custom event */
  event: (name: string, data?: Record<string, string | number | boolean>) => void;
  /** Send a raw payload (advanced) */
  send: (payload: EventPayload) => void;
  /** Identify the current visitor with custom properties */
  identify: (data: Record<string, string | number | boolean>) => void;
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
  if (typeof navigator === "undefined") return false;
  return navigator.doNotTrack === "1" || (navigator as unknown as Record<string, unknown>).globalPrivacyControl === true;
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

// --- Core ---

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
  } = config;

  let enabled = true;
  let currentUrl = "";
  let currentReferrer = "";
  let cleanupFns: Array<() => void> = [];

  // Check if we should track
  function shouldTrack(): boolean {
    if (!enabled) return false;
    if (typeof window === "undefined") return false;
    if (isBot()) return false;
    if (respectDNT && isDNT()) return false;
    if (isLocalhost()) return false;
    if (domains && domains.length > 0) {
      const host = getHostname();
      if (!domains.some((d) => host === d || host.endsWith(`.${d}`))) {
        return false;
      }
    }
    return true;
  }

  // Send data to Umami API
  function sendPayload(eventPayload: EventPayload = {}): void {
    if (!shouldTrack()) return;

    const url = eventPayload.url || getUrl();
    const referrer = eventPayload.referrer || currentReferrer || getReferrer();
    const title = eventPayload.title || getTitle();

    const body: SendBody = {
      type: "event",
      payload: {
        website: websiteId,
        hostname: customHostname || getHostname(),
        screen: getScreen(),
        language: getLanguage(),
        title,
        url,
        referrer,
        ...(eventPayload.name ? { name: eventPayload.name } : {}),
        ...(eventPayload.data ? { data: eventPayload.data } : {}),
        ...(tag ? { tag } : {}),
      },
    };

    // Use sendBeacon when available (doesn't block navigation), fall back to fetch
    const apiUrl = `${baseUrl}${endpoint}`;
    const payload = JSON.stringify(body);

    if (typeof navigator !== "undefined" && navigator.sendBeacon) {
      const blob = new Blob([payload], { type: "application/json" });
      const sent = navigator.sendBeacon(apiUrl, blob);
      if (sent) return;
    }

    // Fallback to fetch
    fetch(apiUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload,
      keepalive: true,
      mode: "cors",
    }).catch(() => {
      // Silently ignore tracking failures
    });
  }

  // Handle route changes for SPAs
  function handleRouteChange(): void {
    const newUrl = getUrl();
    if (newUrl === currentUrl) return;
    currentReferrer = currentUrl;
    currentUrl = newUrl;
    sendPayload({ url: currentUrl, referrer: currentReferrer });
  }

  // Set up auto-tracking
  function setupAutoTrack(): void {
    if (typeof window === "undefined") return;
    if (!autoTrack) return;

    currentUrl = getUrl();
    currentReferrer = getReferrer();

    // Track initial pageview
    sendPayload();

    // Listen for pushState / replaceState / popstate for SPA navigation
    const originalPushState = history.pushState;
    const originalReplaceState = history.replaceState;

    history.pushState = function (...args) {
      originalPushState.apply(this, args);
      // Use setTimeout to let the browser update location
      setTimeout(handleRouteChange, 0);
    };

    history.replaceState = function (...args) {
      originalReplaceState.apply(this, args);
      setTimeout(handleRouteChange, 0);
    };

    const onPopState = () => {
      setTimeout(handleRouteChange, 0);
    };
    window.addEventListener("popstate", onPopState);

    // Track visibility change (user comes back to tab)
    // Not a pageview, but useful for session keepalive

    cleanupFns.push(() => {
      history.pushState = originalPushState;
      history.replaceState = originalReplaceState;
      window.removeEventListener("popstate", onPopState);
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

  // Public API
  return {
    pageview(options) {
      const url = options?.url || getUrl();
      currentReferrer = currentUrl || getReferrer();
      currentUrl = url;
      sendPayload({
        url,
        title: options?.title,
        referrer: options?.referrer || currentReferrer,
      });
    },

    event(name, data) {
      sendPayload({ name, data });
    },

    send(payload) {
      sendPayload(payload);
    },

    identify(data) {
      sendPayload({ name: "identify", data });
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
