import { useContext } from "react";
import type { Tracker } from "@mantecato/tracker";
import { TrackerContext } from "./TrackerContext";

/**
 * Access the tracker instance from within a TrackerProvider.
 *
 * @example
 * ```tsx
 * function Button() {
 *   const { event } = useTracker();
 *   return <button onClick={() => event('cta_click')}>CTA</button>;
 * }
 * ```
 */
export function useTracker(): Tracker {
  const tracker = useContext(TrackerContext);
  if (!tracker) {
    throw new Error("useTracker must be used within a <TrackerProvider>");
  }
  return tracker;
}
