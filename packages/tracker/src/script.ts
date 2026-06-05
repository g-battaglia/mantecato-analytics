/**
 * Drop-in script for <script> tag usage.
 *
 * Usage:
 *   <script defer src="https://your-instance.com/api/script"
 *     data-website-id="your-uuid"
 *     data-host-url="https://your-instance.com"
 *     data-domains="example.com,www.example.com"
 *     data-tag="production"
 *     data-auto-track="true"
 *     data-do-not-track="true"
 *     data-exclude-search="true"
 *     data-exclude-hash="true"
 *     data-before-send="myBeforeSendFn"
 *     data-fetch-credentials="include"
 *   ></script>
 *
 * All data-* attributes are optional except data-website-id.
 * data-host-url defaults to the script's origin.
 *
 * Supports Umami-compatible data-umami-event click tracking:
 *   <button data-umami-event="signup" data-umami-event-plan="pro">Sign up</button>
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

  const domains = script.getAttribute("data-domains")
    ?.split(",")
    .map((d) => d.trim())
    .filter(Boolean);

  const autoTrack = script.getAttribute("data-auto-track") !== "false";
  // Match Umami: data-do-not-track="true" opts IN to DNT checking (default: off)
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
    autoTrack,
    respectDNT,
    domains,
    tag,
    excludeSearch,
    excludeHash,
    beforeSend,
    credentials: fetchCredentials,
  });

  // Data attribute click tracking — supports both data-mantecato-event and data-umami-event
  // <button data-mantecato-event="signup" data-mantecato-event-plan="pro">
  const eventNameAttribute = "data-mantecato-event";
  const eventNameFallback = "data-umami-event";
  const eventRegex = /data-(?:mantecato|umami)-event-([\w-_]+)/;

  function trackElement(el: HTMLElement): Promise<void> {
    const eventName = el.getAttribute(eventNameAttribute) || el.getAttribute(eventNameFallback);
    if (!eventName) return Promise.resolve();

    const eventData: Record<string, string> = {};
    for (const attr of Array.from(el.attributes)) {
      const match = attr.name.match(eventRegex);
      if (match) eventData[match[1]] = attr.value;
    }

    // Return the actual send promise so link click handling can wait for it
    return tracker.event(eventName, Object.keys(eventData).length > 0 ? eventData : undefined);
  }

  function setupEventAttributeTracking() {
    const onClick = (e: MouseEvent) => {
      const el = e.target as HTMLElement;
      const parentElement = el.closest("a,button") as HTMLElement | null;

      if (!parentElement) {
        // No a/button ancestor — try tracking the element itself
        trackElement(el);
        return;
      }

      if (!parentElement.getAttribute(eventNameAttribute) && !parentElement.getAttribute(eventNameFallback)) return;

      if (parentElement.tagName === "BUTTON") {
        trackElement(parentElement);
        return;
      }

      if (parentElement.tagName === "A") {
        const anchor = parentElement as HTMLAnchorElement;
        const href = anchor.href;
        const target = anchor.target;

        if (!href) {
          trackElement(parentElement);
          return;
        }

        const external =
          target === "_blank" ||
          e.ctrlKey ||
          e.shiftKey ||
          e.metaKey ||
          (e.button !== undefined && e.button === 1);

        if (!external) e.preventDefault();

        trackElement(parentElement).then(() => {
          if (!external) {
            if (target === "_top" && typeof top !== "undefined" && top) {
              top.location.href = href;
            } else {
              location.href = href;
            }
          }
        });
      }
    };

    document.addEventListener("click", onClick, true);
  }

  setupEventAttributeTracking();

  // Expose on window for manual usage: mantecato.event('click', { button: 'cta' })
  const w = window as unknown as Record<string, unknown>;
  w.mantecato = tracker;

  // Umami-compatible global — delegates to tracker.track() which has full overload support
  if (!w.umami) {
    w.umami = {
      track: tracker.track,
      identify: tracker.identify,
    };
  }
})();

// Re-export for IIFE global
export type { Tracker };
