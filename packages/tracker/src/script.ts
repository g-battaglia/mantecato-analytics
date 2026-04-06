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
 *     data-respect-dnt="true"
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
  const respectDNT = script.getAttribute("data-respect-dnt") !== "false";
  const tag = script.getAttribute("data-tag") || undefined;

  const tracker = createTracker({
    websiteId,
    baseUrl,
    autoTrack,
    respectDNT,
    domains,
    tag,
  });

  // Umami-compatible data-umami-event click tracking
  // <button data-umami-event="signup" data-umami-event-plan="pro">
  function setupEventAttributeTracking() {
    document.addEventListener("click", (e) => {
      const target = (e.target as HTMLElement)?.closest("[data-umami-event]") as HTMLElement | null;
      if (!target) return;

      const eventName = target.getAttribute("data-umami-event");
      if (!eventName) return;

      // Collect data-umami-event-* attributes as event data
      const data: Record<string, string> = {};
      const prefix = "data-umami-event-";
      for (const attr of Array.from(target.attributes)) {
        if (attr.name.startsWith(prefix) && attr.name.length > prefix.length) {
          const key = attr.name.slice(prefix.length);
          data[key] = attr.value;
        }
      }

      tracker.event(eventName, Object.keys(data).length > 0 ? data : undefined);
    });
  }

  setupEventAttributeTracking();

  // Expose on window for manual usage: mantecato.event('click', { button: 'cta' })
  const w = window as unknown as Record<string, unknown>;
  w.mantecato = tracker;

  // Umami-compatible global
  if (!w.umami) {
    w.umami = {
      track: (nameOrFn?: string | ((props: Record<string, unknown>) => Record<string, unknown>), data?: Record<string, string | number | boolean>) => {
        if (typeof nameOrFn === "function") {
          const result = nameOrFn({});
          const eventName = (result as Record<string, unknown>).name as string | undefined;
          const eventData = (result as Record<string, unknown>).data as Record<string, string | number | boolean> | undefined;
          if (eventName) {
            tracker.event(eventName, eventData);
          } else {
            tracker.pageview();
          }
        } else if (nameOrFn) {
          tracker.event(nameOrFn, data);
        } else {
          tracker.pageview();
        }
      },
      identify: (idOrData: string | Record<string, string | number | boolean>, data?: Record<string, string | number | boolean>) => {
        if (typeof idOrData === "string") {
          tracker.identify(idOrData, data);
        } else {
          tracker.identify(idOrData);
        }
      },
    };
  }
})();

// Re-export for IIFE global
export type { Tracker };
