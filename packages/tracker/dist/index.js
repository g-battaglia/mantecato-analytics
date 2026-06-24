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
function getReferrer() {
  if (typeof document === "undefined") return "";
  return document.referrer || "";
}
function isDNT() {
  const w = typeof window !== "undefined" ? window : {};
  const n = typeof navigator !== "undefined" ? navigator : {};
  const dnt = w.doNotTrack || n.doNotTrack || n.msDoNotTrack;
  return dnt === 1 || dnt === "1" || dnt === "yes" || dnt === true;
}
function isGPC() {
  const n = typeof navigator !== "undefined" ? navigator : {};
  return n.globalPrivacyControl === true;
}
function isBot() {
  if (typeof navigator === "undefined") return false;
  if (navigator.webdriver === true) return true;
  return /bot|crawl|spider|slurp|lighthouse|headless/i.test(navigator.userAgent);
}
var SPA_DELAY = 300;
function createTracker(config) {
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
    heartbeatMs = 15e3
  } = config;
  let enabled = true;
  let currentUrl = "";
  let cleanupFns = [];
  let activeMs = 0;
  let activeStart = 0;
  let heartbeatTimer = null;
  function isVisible() {
    return typeof document === "undefined" || document.visibilityState !== "hidden";
  }
  function startActive() {
    if (activeStart === 0 && isVisible()) activeStart = Date.now();
  }
  function stopActive() {
    if (activeStart !== 0) {
      activeMs += Date.now() - activeStart;
      activeStart = 0;
    }
  }
  function activeSeconds() {
    let ms = activeMs;
    if (activeStart !== 0) ms += Date.now() - activeStart;
    return Math.round(ms / 1e3);
  }
  function resetActive() {
    activeMs = 0;
    activeStart = isVisible() ? Date.now() : 0;
  }
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
    if (respectGPC && isGPC()) return false;
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
    const referrer = getReferrer();
    return {
      website: websiteId,
      hostname: customHostname || getHostname(),
      title,
      url,
      ...referrer ? { referrer } : {},
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
  function sendEngagement() {
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
        seconds
      }
    });
    const apiUrl = `${baseUrl}${endpoint}`;
    try {
      void fetch(apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        keepalive: true,
        credentials: "omit"
      });
    } catch {
    }
  }
  function nextPage() {
    sendEngagement();
    resetActive();
  }
  function onVisibility() {
    if (isVisible()) {
      startActive();
    } else {
      stopActive();
      sendEngagement();
    }
  }
  function onPageHide() {
    stopActive();
    sendEngagement();
  }
  function setupEngagement() {
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
  function handlePush(_state, _title, url) {
    if (!url) return;
    const newUrl = normalize(new URL(String(url), typeof location !== "undefined" ? location.href : void 0).toString());
    if (newUrl !== currentUrl) {
      nextPage();
      currentUrl = newUrl;
      setTimeout(() => send(buildPayload()), SPA_DELAY);
    }
  }
  function setupAutoTrack() {
    if (typeof window === "undefined") return;
    if (!autoTrack) return;
    currentUrl = normalize(typeof location !== "undefined" ? location.href : "");
    send(buildPayload());
    setupEngagement();
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
      if (url !== currentUrl) nextPage();
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