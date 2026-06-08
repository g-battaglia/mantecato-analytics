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
interface TrackerConfig {
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
interface EventPayload {
    /** Override page URL */
    url?: string;
    /** Override page title */
    title?: string;
}
interface UmamiPayload {
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
/** Function that receives default payload and returns a modified payload */
type TrackCallback = (props: UmamiPayload) => UmamiPayload;
interface Tracker {
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
declare function createTracker(config: TrackerConfig): Tracker;

export { type EventPayload, type TrackCallback, type Tracker, type TrackerConfig, type UmamiPayload, createTracker };
