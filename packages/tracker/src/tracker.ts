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
  /** Respect the legacy Do-Not-Track signal (default: false — DNT is not legally binding) */
  respectDNT?: boolean;
  /** Respect Global Privacy Control, a legally-recognised opt-out signal (default: true) */
  respectGPC?: boolean;
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
  /** Track on-page engagement (active time) for accurate duration + bounce (default: true) */
  engagement?: boolean;
  /** Periodic engagement heartbeat interval (ms) while the tab is visible; 0 disables (default: 15000) */
  heartbeatMs?: number;
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
  /** Referring URL (reduced to its domain server-side; same-site dropped). */
  referrer?: string;
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

function getReferrer(): string {
  if (typeof document === "undefined") return "";
  return document.referrer || "";
}

// Legacy Do-Not-Track header signal. Abandoned W3C standard, not legally binding
// anywhere — honoured only when explicitly opted in (``respectDNT``).
function isDNT(): boolean {
  const w = typeof window !== "undefined" ? (window as unknown as Record<string, unknown>) : {};
  const n = typeof navigator !== "undefined" ? (navigator as unknown as Record<string, unknown>) : {};
  const dnt = w.doNotTrack || n.doNotTrack || n.msDoNotTrack;
  return dnt === 1 || dnt === "1" || dnt === "yes" || dnt === true;
}

// Global Privacy Control — a legally-recognised opt-out signal under CCPA/CPRA and
// several US state privacy laws. Honoured by default (``respectGPC``).
function isGPC(): boolean {
  const n = typeof navigator !== "undefined" ? (navigator as unknown as Record<string, unknown>) : {};
  return n.globalPrivacyControl === true;
}

function isBot(): boolean {
  if (typeof navigator === "undefined") return false;
  if ((navigator as unknown as { webdriver?: boolean }).webdriver === true) return true;
  return /bot|crawl|spider|slurp|lighthouse|headless/i.test(navigator.userAgent);
}

// --- Core ---

const SPA_DELAY = 300;

export function createTracker(config: TrackerConfig): Tracker {
  const {
    websiteId,
    baseUrl,
    endpoint = "/api/send",
    autoTrack = true,
    respectDNT = false,
    respectGPC = true,
    domains,
    hostname: customHostname,
    tag,
    excludeSearch = false,
    excludeHash = false,
    beforeSend,
    credentials = "omit",
    engagement = true,
    heartbeatMs = 15000,
  } = config;

  let enabled = true;
  let currentUrl = "";
  let cleanupFns: Array<() => void> = [];

  // --- Engagement: cumulative active (tab-visible) time on the current page ---
  let activeMs = 0;
  let activeStart = 0;
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null;

  function isVisible(): boolean {
    return typeof document === "undefined" || document.visibilityState !== "hidden";
  }
  function startActive(): void {
    if (activeStart === 0 && isVisible()) activeStart = Date.now();
  }
  function stopActive(): void {
    if (activeStart !== 0) {
      activeMs += Date.now() - activeStart;
      activeStart = 0;
    }
  }
  function activeSeconds(): number {
    let ms = activeMs;
    if (activeStart !== 0) ms += Date.now() - activeStart;
    return Math.round(ms / 1000);
  }
  function resetActive(): void {
    activeMs = 0;
    activeStart = isVisible() ? Date.now() : 0;
  }

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
    if (respectGPC && isGPC()) return false;
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
    const referrer = getReferrer();

    return {
      website: websiteId,
      hostname: customHostname || getHostname(),
      title,
      url,
      ...(referrer ? { referrer } : {}),
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

  function sendEngagement(): void {
    if (!engagement || !shouldTrack()) return;
    const seconds = activeSeconds();
    if (seconds <= 0) return;
    const url = currentUrl || normalize(getUrl());
    const body = JSON.stringify({
      type: "engagement",
      payload: {
        website: websiteId,
        hostname: customHostname || getHostname(),
        url,
        seconds,
      },
    });
    const apiUrl = `${baseUrl}${endpoint}`;
    try {
      // Use keepalive fetch instead of sendBeacon: the Beacon API fixes
      // credentials to "include", which can leak existing first-party cookies to
      // same-origin/proxied collectors. The tracker guarantee is no cookies.
      void fetch(apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        keepalive: true,
        credentials: "omit",
      });
    } catch {
      // Silently ignore tracking failures
    }
  }

  // Attribute accrued active time to the page that is ending, then start timing
  // the new page. Called on every route change (SPA, popstate, manual pageview).
  function nextPage(): void {
    sendEngagement();
    resetActive();
  }

  function onVisibility(): void {
    if (isVisible()) {
      startActive();
    } else {
      stopActive();
      sendEngagement();
    }
  }
  function onPageHide(): void {
    stopActive();
    sendEngagement();
  }

  function setupEngagement(): void {
    if (!engagement) return;
    if (typeof document === "undefined" || typeof window === "undefined") return;
    resetActive();
    document.addEventListener("visibilitychange", onVisibility, true);
    window.addEventListener("pagehide", onPageHide, true);
    if (heartbeatMs > 0) {
      heartbeatTimer = setInterval(() => {
        if (isVisible()) sendEngagement();
      }, heartbeatMs);
    }
    cleanupFns.push(() => {
      document.removeEventListener("visibilitychange", onVisibility, true);
      window.removeEventListener("pagehide", onPageHide, true);
      if (heartbeatTimer !== null) {
        clearInterval(heartbeatTimer);
        heartbeatTimer = null;
      }
    });
  }

  function handlePush(_state: unknown, _title: unknown, url?: string | URL | null): void {
    if (!url) return;
    const newUrl = normalize(new URL(String(url), typeof location !== "undefined" ? location.href : undefined).toString());
    if (newUrl !== currentUrl) {
      nextPage();
      currentUrl = newUrl;
      setTimeout(() => send(buildPayload()), SPA_DELAY);
    }
  }

  function setupAutoTrack(): void {
    if (typeof window === "undefined") return;
    if (!autoTrack) return;

    currentUrl = normalize(typeof location !== "undefined" ? location.href : "");

    send(buildPayload());
    setupEngagement();

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
          nextPage();
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
      if (url !== currentUrl) nextPage();
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
