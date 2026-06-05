/**
 * @mantecato/tracker
 *
 * Analytics tracking script for Mantecato.
 * Wire-compatible with the Umami /api/send endpoint.
 *
 * Usage (npm):
 *   import { createTracker } from '@mantecato/tracker';
 *   const tracker = createTracker({ websiteId: '...', baseUrl: 'https://your-instance.com' });
 *   tracker.pageview();
 *   tracker.event('signup', { plan: 'pro' });
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
    /** Respect Do-Not-Track browser setting (default: true) */
    respectDNT?: boolean;
    /** Domains to track — if set, only track on these domains (default: track all) */
    domains?: string[];
    /** Custom hostname override */
    hostname?: string;
    /** Tag to identify this tracker instance */
    tag?: string;
    /** Enable session replay data collection — click coordinates, scroll depth (default: false) */
    sessionReplay?: boolean;
    /** Strip query string from tracked URLs (default: false) */
    excludeSearch?: boolean;
    /** Strip hash from tracked URLs (default: false) */
    excludeHash?: boolean;
    /** Callback invoked before each send — return modified payload or falsy to cancel */
    beforeSend?: (type: string, payload: UmamiPayload) => UmamiPayload | false | null | undefined | Promise<UmamiPayload | false | null | undefined>;
    /** Fetch credentials mode (default: "omit") */
    credentials?: RequestCredentials;
}
interface RevenueData {
    /** Revenue amount */
    amount: number;
    /** ISO 4217 currency code (e.g. "USD", "EUR") */
    currency: string;
}
interface EventPayload {
    /** Custom event name */
    name?: string;
    /** Custom event data (key-value pairs) */
    data?: Record<string, string | number | boolean>;
    /** Override page URL */
    url?: string;
    /** Override page title */
    title?: string;
    /** Override referrer */
    referrer?: string;
    /** Revenue data for this event */
    revenue?: RevenueData;
}
interface UmamiPayload {
    website: string;
    hostname: string;
    screen: string;
    language: string;
    title: string;
    url: string;
    referrer: string;
    name?: string;
    data?: Record<string, string | number | boolean>;
    tag?: string;
    revenue?: RevenueData;
    id?: string;
}
/** Function that receives default payload and returns a modified payload */
type TrackCallback = (props: UmamiPayload) => UmamiPayload;
interface Tracker {
    /** Track a pageview for the current URL (or override with options) */
    pageview: (options?: Pick<EventPayload, "url" | "title" | "referrer">) => Promise<void>;
    /** Track a custom event */
    event: (name: string, data?: Record<string, string | number | boolean>) => Promise<void>;
    /** Track a revenue event */
    revenue: (amount: number, currency: string, data?: Record<string, string | number | boolean>) => Promise<void>;
    /** Send a raw payload (advanced) */
    send: (payload: EventPayload) => Promise<void>;
    /** Umami-compatible track() — overloaded: no args = pageview, string = event, object = raw payload, function = callback */
    track: {
        (): Promise<void>;
        (name: string, data?: Record<string, string | number | boolean>): Promise<void>;
        (payload: Partial<UmamiPayload>): Promise<void>;
        (callback: TrackCallback): Promise<void>;
    };
    /** Identify the current visitor — accepts data object or (id, data) like Umami */
    identify: {
        (data: Record<string, string | number | boolean>): Promise<void>;
        (id: string, data?: Record<string, string | number | boolean>): Promise<void>;
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

export { type EventPayload, type RevenueData, type TrackCallback, type Tracker, type TrackerConfig, type UmamiPayload, createTracker };
