/**
 * Drop-in script for <script> tag usage.
 *
 * Usage:
 *   <script defer src="https://your-instance.com/api/script"
 *     data-website-id="your-uuid"
 *     data-host-url="https://your-instance.com"
 *     data-endpoint="/api/send"
 *     data-domains="example.com,www.example.com"
 *     data-tag="production"
 *     data-auto-track="true"
 *     data-respect-gpc="false"
 *     data-do-not-track="true"
 *     data-exclude-search="true"
 *     data-exclude-hash="true"
 *     data-before-send="myBeforeSendFn"
 *     data-fetch-credentials="omit"
 *   ></script>
 *
 * All data-* attributes are optional except data-website-id.
 * data-host-url defaults to the script's origin.
 *
 * Supports Umami-compatible data-umami-event click tracking. Event
 * properties are intentionally ignored:
 *   <button data-umami-event="signup">Sign up</button>
 */

import { createTracker, type Tracker } from "./tracker";

(function () {
  if (typeof document === "undefined") return;

  // Find our script tag
  const script =
    document.currentScript as HTMLScriptElement | null ??
    document.querySelector<HTMLScriptElement>("script[data-website-id]");

  if (!script) {
    console.warn("[mantecato] No script tag found with data-website-id");
    return;
  }

  const websiteId = script.getAttribute("data-website-id");
  if (!websiteId) {
    console.warn("[mantecato] data-website-id is required");
    return;
  }

  // Resolve base URL: explicit attribute, or the script's own origin
  let baseUrl = script.getAttribute("data-host-url") || "";
  if (!baseUrl) {
    try {
      const scriptUrl = new URL(script.src);
      baseUrl = scriptUrl.origin;
    } catch {
      baseUrl = location.origin;
    }
  }
  baseUrl = baseUrl.replace(/\/+$/, "");

  // Ingest path. Override to serve the API first-party behind a reverse proxy
  // (a same-origin path dodges ad-blockers that block known analytics endpoints).
  const endpoint = script.getAttribute("data-endpoint") || undefined;

  const domains = script.getAttribute("data-domains")
    ?.split(",")
    .map((d) => d.trim())
    .filter(Boolean);

  const autoTrack = script.getAttribute("data-auto-track") !== "false";
  // Privacy-first: honour Global Privacy Control by default — GPC is a legally
  // recognised opt-out signal (CCPA/CPRA and US state laws). Opt OUT with
  // data-respect-gpc="false". The legacy DNT header is not legally binding, so it
  // is ignored by default; opt IN with data-do-not-track="true" (matches Umami).
  const respectGPC = script.getAttribute("data-respect-gpc") !== "false";
  const respectDNT = script.getAttribute("data-do-not-track") === "true";
  const tag = script.getAttribute("data-tag") || undefined;
  const excludeSearch = script.getAttribute("data-exclude-search") === "true";
  const excludeHash = script.getAttribute("data-exclude-hash") === "true";
  const beforeSendAttr = script.getAttribute("data-before-send") || undefined;
  const fetchCredentials = (script.getAttribute("data-fetch-credentials") || "omit") as RequestCredentials;

  // beforeSend: look up a global function by name, matching Umami behavior
  const beforeSend = beforeSendAttr
    ? (type: string, payload: import("./tracker").UmamiPayload) => {
        const fn = (window as unknown as Record<string, unknown>)[beforeSendAttr];
        if (typeof fn === "function") return fn(type, payload);
        return payload;
      }
    : undefined;

  const tracker = createTracker({
    websiteId,
    baseUrl,
    endpoint,
    autoTrack,
    respectGPC,
    respectDNT,
    domains,
    tag,
    excludeSearch,
    excludeHash,
    beforeSend,
    credentials: fetchCredentials,
  });

  const w = window as unknown as Record<string, unknown>;
  w.mantecato = tracker;
  w.umami = tracker;

  document.addEventListener("click", (event) => {
    const target = event.target instanceof Element
      ? event.target.closest<HTMLElement>("[data-umami-event]")
      : null;
    const name = target?.getAttribute("data-umami-event")?.trim();
    if (name) void tracker.event(name);
  }, true);
})();

// Re-export for IIFE global
export type { Tracker };
