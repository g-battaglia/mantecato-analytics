import { useEffect, useRef } from "react";
import { useTracker } from "./useTracker";

/**
 * Track a pageview when the component mounts or when the URL changes.
 *
 * @param url - Override the tracked URL (defaults to current page)
 * @param title - Override the tracked title
 *
 * @example
 * ```tsx
 * function Page() {
 *   usePageview();
 *   return <div>Page content</div>;
 * }
 *
 * // With explicit URL (e.g. for dynamic routes)
 * function ProductPage({ slug }: { slug: string }) {
 *   usePageview(`/products/${slug}`);
 *   return <div>Product: {slug}</div>;
 * }
 * ```
 */
export function usePageview(url?: string, title?: string): void {
  const tracker = useTracker();
  const trackedRef = useRef<string | undefined>(undefined);

  useEffect(() => {
    // Avoid duplicate tracking for the same URL
    const trackUrl = url ?? (typeof window !== "undefined" ? window.location.pathname + window.location.search : undefined);
    if (trackedRef.current === trackUrl) return;
    trackedRef.current = trackUrl;

    tracker.pageview({ url: trackUrl, title });
  }, [tracker, url, title]);
}
