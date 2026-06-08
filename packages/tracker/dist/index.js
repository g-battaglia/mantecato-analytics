// src/tracker.ts
function getHostname() {
  if (typeof location === "undefined") return "";
  return location.hostname;
}
function getUrl() {
  if (typeof location === "undefined") return "";
  return location.pathname + location.search + (location.hash || "");
}
function getTitle() {
  if (typeof document === "undefined") return "";
  return document.title;
}
function isDNT() {
  const w = typeof window !== "undefined" ? window : {};
  const n = typeof navigator !== "undefined" ? navigator : {};
  const dnt = w.doNotTrack || n.doNotTrack || n.msDoNotTrack || n.globalPrivacyControl;
  return dnt === 1 || dnt === "1" || dnt === "yes" || dnt === true;
}
function isBot() {
  if (typeof navigator === "undefined") return false;
  return /bot|crawl|spider|slurp|lighthouse/i.test(navigator.userAgent);
}
var SPA_DELAY = 300;
function createTracker(config) {
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
    credentials = "omit"
  } = config;
  let enabled = true;
  let currentUrl = "";
  let cleanupFns = [];
  function normalize(raw) {
    if (!raw) return raw;
    try {
      const u = new URL(raw, typeof location !== "undefined" ? location.href : void 0);
      if (excludeSearch) u.search = "";
      if (excludeHash) u.hash = "";
      return u.toString();
    } catch {
      return raw;
    }
  }
  function shouldTrack() {
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
  function buildPayload(eventPayload = {}) {
    const url = normalize(eventPayload.url || getUrl());
    const title = eventPayload.title || getTitle();
    return {
      website: websiteId,
      hostname: customHostname || getHostname(),
      title,
      url,
      ...tag ? { tag } : {}
    };
  }
  function sanitizePayload(payload) {
    const base = buildPayload({
      url: payload.url,
      title: payload.title
    });
    const name = typeof payload.name === "string" ? payload.name.trim().slice(0, 100) : "";
    return {
      ...base,
      hostname: payload.hostname || base.hostname,
      ...name ? { name } : {},
      ...tag ? { tag } : {}
    };
  }
  async function send(payload) {
    if (!shouldTrack()) return;
    let finalPayload = payload;
    if (beforeSend) {
      finalPayload = await Promise.resolve(beforeSend("event", payload));
      if (!finalPayload) return;
    }
    const apiUrl = `${baseUrl}${endpoint}`;
    const body = { type: "event", payload: sanitizePayload(finalPayload) };
    try {
      await fetch(apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        keepalive: true,
        credentials
      });
    } catch {
    }
  }
  function handlePush(_state, _title, url) {
    if (!url) return;
    const newUrl = normalize(new URL(String(url), typeof location !== "undefined" ? location.href : void 0).toString());
    if (newUrl !== currentUrl) {
      currentUrl = newUrl;
      setTimeout(() => send(buildPayload()), SPA_DELAY);
    }
  }
  function setupAutoTrack() {
    if (typeof window === "undefined") return;
    if (!autoTrack) return;
    currentUrl = normalize(typeof location !== "undefined" ? location.href : "");
    send(buildPayload());
    const originalPushState = history.pushState;
    const originalReplaceState = history.replaceState;
    history.pushState = function(...args) {
      handlePush(args[0], args[1], args[2]);
      return originalPushState.apply(this, args);
    };
    history.replaceState = function(...args) {
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
  function init() {
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
    track(payloadOrFn) {
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
        try {
          fn();
        } catch {
        }
      }
      cleanupFns = [];
    }
  };
}
export {
  createTracker
};
//# sourceMappingURL=index.js.map