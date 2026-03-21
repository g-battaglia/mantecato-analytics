/**
 * Drop-in script for <script> tag usage.
 *
 * Usage:
 *   <script defer src="https://your-umami.com/mantecato.js"
 *     data-website-id="your-uuid"
 *     data-host-url="https://your-umami.com"
 *     data-domains="example.com,www.example.com"
 *     data-tag="production"
 *     data-auto-track="true"
 *     data-respect-dnt="true"
 *   ></script>
 *
 * All data-* attributes are optional except data-website-id.
 * data-host-url defaults to the script's origin.
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
  // Remove trailing slash
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

  // Expose on window for manual usage: mantecato.event('click', { button: 'cta' })
  const w = window as unknown as Record<string, unknown>;
  w.mantecato = tracker;

  // Also expose Umami-compatible global
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
      identify: (data: Record<string, string | number | boolean>) => {
        tracker.identify(data);
      },
    };
  }
})();

// Re-export for IIFE global
export type { Tracker };
