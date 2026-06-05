"use strict";
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/index.ts
var index_exports = {};
__export(index_exports, {
  createTracker: () => createTracker
});
module.exports = __toCommonJS(index_exports);

// src/tracker.ts
function getScreen() {
  if (typeof screen === "undefined") return "";
  return `${screen.width}x${screen.height}`;
}
function getLanguage() {
  if (typeof navigator === "undefined") return "";
  return navigator.language || "";
}
function getHostname() {
  if (typeof location === "undefined") return "";
  return location.hostname;
}
function getUrl() {
  if (typeof location === "undefined") return "";
  return location.pathname + location.search + (location.hash || "");
}
function getReferrer() {
  if (typeof document === "undefined") return "";
  return document.referrer;
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
function isLocalhost() {
  if (typeof location === "undefined") return false;
  return location.hostname === "localhost" || location.hostname === "127.0.0.1" || location.hostname === "::1";
}
function isDisabledByUser() {
  try {
    return localStorage.getItem("mantecato.disabled") === "1" || localStorage.getItem("umami.disabled") === "1";
  } catch {
    return false;
  }
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
    sessionReplay = false,
    excludeSearch = false,
    excludeHash = false,
    beforeSend,
    credentials = "omit"
  } = config;
  let enabled = true;
  let disabled = false;
  let currentUrl = "";
  let currentReferrer = "";
  let cache = "";
  let identity = "";
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
  function buildPayload(eventPayload = {}) {
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
      ...eventPayload.name ? { name: eventPayload.name } : {},
      ...eventPayload.data ? { data: eventPayload.data } : {},
      ...eventPayload.revenue ? { revenue: eventPayload.revenue } : {},
      ...tag ? { tag } : {},
      ...identity ? { id: identity } : {}
    };
  }
  async function send(payload, type = "event") {
    if (!shouldTrack()) return;
    let finalPayload = payload;
    if (beforeSend) {
      finalPayload = await Promise.resolve(beforeSend(type, payload));
      if (!finalPayload) return;
    }
    const apiUrl = `${baseUrl}${endpoint}`;
    const body = { type, payload: finalPayload };
    const jsonBody = JSON.stringify(body);
    const headers = { "Content-Type": "application/json" };
    if (cache) {
      headers["x-umami-cache"] = cache;
    }
    try {
      const res = await fetch(apiUrl, {
        method: "POST",
        headers,
        body: jsonBody,
        keepalive: true,
        credentials
      });
      const data = await res.json();
      if (data) {
        if (data.cache) cache = data.cache;
        if (data.disabled) disabled = true;
      }
    } catch {
    }
  }
  function getOrigin() {
    if (typeof location === "undefined") return "";
    return location.origin || "";
  }
  function handlePush(_state, _title, url) {
    if (!url) return;
    const newUrl = normalize(new URL(String(url), typeof location !== "undefined" ? location.href : void 0).toString());
    if (newUrl !== currentUrl) {
      currentReferrer = currentUrl;
      currentUrl = newUrl;
      setTimeout(() => send(buildPayload()), SPA_DELAY);
    }
  }
  function setupAutoTrack() {
    if (typeof window === "undefined") return;
    if (!autoTrack) return;
    currentUrl = normalize(typeof location !== "undefined" ? location.href : "");
    const ref = getReferrer();
    currentReferrer = normalize(ref.startsWith(getOrigin()) ? "" : ref);
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
  function setupSessionReplay() {
    if (typeof window === "undefined" || typeof document === "undefined") return;
    if (!sessionReplay) return;
    const onClick = (e) => {
      if (!shouldTrack()) return;
      const target = e.target;
      const selector = target?.tagName?.toLowerCase() || "unknown";
      send(buildPayload({
        name: "_replay_click",
        data: {
          x: e.clientX,
          y: e.clientY,
          target: selector,
          ...target?.id ? { id: target.id } : {}
        }
      }));
    };
    let scrollTimer = null;
    const onScroll = () => {
      if (!shouldTrack()) return;
      if (scrollTimer) clearTimeout(scrollTimer);
      scrollTimer = setTimeout(() => {
        const scrollTop = window.scrollY || document.documentElement.scrollTop;
        const docHeight = Math.max(
          document.body.scrollHeight,
          document.documentElement.scrollHeight
        );
        const winHeight = window.innerHeight;
        const depth = docHeight > winHeight ? Math.round(scrollTop / (docHeight - winHeight) * 100) : 100;
        send(buildPayload({
          name: "_replay_scroll",
          data: { depth, scrollTop: Math.round(scrollTop) }
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
  function init() {
    if (initialized) return;
    initialized = true;
    setupAutoTrack();
    if (sessionReplay) setupSessionReplay();
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
      currentReferrer = currentUrl || getReferrer();
      currentUrl = url;
      return send(buildPayload({
        url,
        title: options?.title,
        referrer: options?.referrer || currentReferrer
      }));
    },
    event(name, data) {
      return send(buildPayload({ name, data }));
    },
    revenue(amount, currency, data) {
      return send(buildPayload({
        name: "revenue",
        data: data || {},
        revenue: { amount, currency }
      }));
    },
    send(payload) {
      return send(buildPayload(payload));
    },
    track(nameOrPayloadOrFn, data) {
      if (typeof nameOrPayloadOrFn === "string") {
        return send(buildPayload({ name: nameOrPayloadOrFn, data }));
      } else if (typeof nameOrPayloadOrFn === "function") {
        return send(nameOrPayloadOrFn(buildPayload()));
      } else if (typeof nameOrPayloadOrFn === "object") {
        return send({ ...nameOrPayloadOrFn });
      } else {
        return send(buildPayload());
      }
    },
    identify(idOrData, data) {
      if (typeof idOrData === "string") {
        identity = idOrData;
        cache = "";
        return send(
          buildPayload({ data: data ?? void 0 }),
          "identify"
        );
      } else {
        cache = "";
        return send(
          buildPayload({ data: idOrData }),
          "identify"
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
        try {
          fn();
        } catch {
        }
      }
      cleanupFns = [];
    }
  };
}
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  createTracker
});
//# sourceMappingURL=index.cjs.map