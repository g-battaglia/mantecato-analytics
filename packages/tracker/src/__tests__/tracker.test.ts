import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createTracker, type Tracker, type TrackerConfig } from "../tracker";

// Capture all sendBeacon / fetch calls
let sentPayloads: Array<{ url: string; body: string }> = [];

function makeConfig(overrides: Partial<TrackerConfig> = {}): TrackerConfig {
  return {
    websiteId: "test-site-id",
    baseUrl: "https://analytics.example.com",
    autoTrack: false,
    ...overrides,
  };
}

function lastPayload() {
  const last = sentPayloads[sentPayloads.length - 1];
  if (!last) throw new Error("No payload sent");
  return JSON.parse(last.body);
}

beforeEach(() => {
  sentPayloads = [];

  // Make sendBeacon return false so we fall through to fetch
  Object.defineProperty(navigator, "sendBeacon", {
    value: vi.fn(() => false),
    writable: true,
    configurable: true,
  });

  // Override fetch to capture payloads
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      sentPayloads.push({ url, body: (init?.body as string) || "" });
      return new Response("ok");
    }),
  );

  // Reset location and userAgent
  Object.defineProperty(window, "location", {
    value: {
      hostname: "example.com",
      pathname: "/page",
      search: "",
      href: "https://example.com/page",
    },
    writable: true,
    configurable: true,
  });

  Object.defineProperty(navigator, "userAgent", {
    value: "Mozilla/5.0 Test Browser",
    writable: true,
    configurable: true,
  });

  Object.defineProperty(navigator, "doNotTrack", {
    value: "0",
    writable: true,
    configurable: true,
  });

  Object.defineProperty(navigator, "language", {
    value: "en-US",
    writable: true,
    configurable: true,
  });

  Object.defineProperty(document, "title", {
    value: "Test Page",
    writable: true,
    configurable: true,
  });

  Object.defineProperty(document, "referrer", {
    value: "",
    writable: true,
    configurable: true,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("createTracker", () => {
  it("creates a tracker with all methods", () => {
    const tracker = createTracker(makeConfig());
    expect(tracker.pageview).toBeTypeOf("function");
    expect(tracker.event).toBeTypeOf("function");
    expect(tracker.revenue).toBeTypeOf("function");
    expect(tracker.send).toBeTypeOf("function");
    expect(tracker.identify).toBeTypeOf("function");
    expect(tracker.enable).toBeTypeOf("function");
    expect(tracker.disable).toBeTypeOf("function");
    expect(tracker.isEnabled).toBeTypeOf("function");
    expect(tracker.destroy).toBeTypeOf("function");
  });

  it("starts enabled", () => {
    const tracker = createTracker(makeConfig());
    expect(tracker.isEnabled()).toBe(true);
  });
});

describe("pageview", () => {
  it("sends a pageview with correct payload", () => {
    const tracker = createTracker(makeConfig());
    tracker.pageview();

    const payload = lastPayload();
    expect(payload.type).toBe("event");
    expect(payload.payload.website).toBe("test-site-id");
    expect(payload.payload.url).toBe("/page");
    expect(payload.payload.hostname).toBe("example.com");
    expect(payload.payload.language).toBe("en-US");
    expect(payload.payload.title).toBe("Test Page");
  });

  it("allows overriding url, title, referrer", () => {
    const tracker = createTracker(makeConfig());
    tracker.pageview({ url: "/custom", title: "Custom", referrer: "https://google.com" });

    const payload = lastPayload();
    expect(payload.payload.url).toBe("/custom");
    expect(payload.payload.title).toBe("Custom");
    expect(payload.payload.referrer).toBe("https://google.com");
  });

  it("sends to correct API endpoint", () => {
    const tracker = createTracker(makeConfig());
    tracker.pageview();

    expect(sentPayloads[0].url).toBe("https://analytics.example.com/api/send");
  });

  it("uses custom endpoint when configured", () => {
    const tracker = createTracker(makeConfig({ endpoint: "/custom/track" }));
    tracker.pageview();

    expect(sentPayloads[0].url).toBe("https://analytics.example.com/custom/track");
  });
});

describe("event", () => {
  it("sends a custom event", () => {
    const tracker = createTracker(makeConfig());
    tracker.event("signup", { plan: "pro" });

    const payload = lastPayload();
    expect(payload.payload.name).toBe("signup");
    expect(payload.payload.data).toEqual({ plan: "pro" });
  });

  it("sends event without data", () => {
    const tracker = createTracker(makeConfig());
    tracker.event("click");

    const payload = lastPayload();
    expect(payload.payload.name).toBe("click");
    expect(payload.payload.data).toBeUndefined();
  });
});

describe("revenue", () => {
  it("sends a revenue event with amount and currency", () => {
    const tracker = createTracker(makeConfig());
    tracker.revenue(29.99, "USD");

    const payload = lastPayload();
    expect(payload.payload.name).toBe("revenue");
    expect(payload.payload.revenue).toEqual({ amount: 29.99, currency: "USD" });
  });

  it("includes extra data with revenue event", () => {
    const tracker = createTracker(makeConfig());
    tracker.revenue(100, "EUR", { product: "widget" });

    const payload = lastPayload();
    expect(payload.payload.name).toBe("revenue");
    expect(payload.payload.revenue).toEqual({ amount: 100, currency: "EUR" });
    expect(payload.payload.data).toEqual({ product: "widget" });
  });
});

describe("identify", () => {
  it("sends identify event with data", () => {
    const tracker = createTracker(makeConfig());
    tracker.identify({ userId: "abc123", plan: "enterprise" });

    const payload = lastPayload();
    expect(payload.payload.name).toBe("identify");
    expect(payload.payload.data).toEqual({ userId: "abc123", plan: "enterprise" });
  });
});

describe("enable/disable", () => {
  it("stops sending when disabled", () => {
    const tracker = createTracker(makeConfig());
    tracker.disable();
    tracker.pageview();

    expect(sentPayloads).toHaveLength(0);
  });

  it("resumes sending when re-enabled", () => {
    const tracker = createTracker(makeConfig());
    tracker.disable();
    tracker.pageview();
    expect(sentPayloads).toHaveLength(0);

    tracker.enable();
    tracker.pageview();
    expect(sentPayloads).toHaveLength(1);
  });

  it("reports enabled state correctly", () => {
    const tracker = createTracker(makeConfig());
    expect(tracker.isEnabled()).toBe(true);
    tracker.disable();
    expect(tracker.isEnabled()).toBe(false);
    tracker.enable();
    expect(tracker.isEnabled()).toBe(true);
  });
});

describe("destroy", () => {
  it("disables tracking on destroy", () => {
    const tracker = createTracker(makeConfig());
    tracker.destroy();
    expect(tracker.isEnabled()).toBe(false);
    tracker.pageview();
    expect(sentPayloads).toHaveLength(0);
  });
});

describe("DNT", () => {
  it("respects Do-Not-Track when enabled", () => {
    Object.defineProperty(navigator, "doNotTrack", {
      value: "1",
      writable: true,
      configurable: true,
    });

    const tracker = createTracker(makeConfig({ respectDNT: true }));
    tracker.pageview();

    expect(sentPayloads).toHaveLength(0);
  });

  it("ignores DNT when respectDNT is false", () => {
    Object.defineProperty(navigator, "doNotTrack", {
      value: "1",
      writable: true,
      configurable: true,
    });

    const tracker = createTracker(makeConfig({ respectDNT: false }));
    tracker.pageview();

    expect(sentPayloads).toHaveLength(1);
  });
});

describe("bot detection", () => {
  it("does not track bots", () => {
    Object.defineProperty(navigator, "userAgent", {
      value: "Googlebot/2.1",
      writable: true,
      configurable: true,
    });

    const tracker = createTracker(makeConfig());
    tracker.pageview();

    expect(sentPayloads).toHaveLength(0);
  });
});

describe("localhost filtering", () => {
  it("does not track on localhost", () => {
    Object.defineProperty(window, "location", {
      value: { hostname: "localhost", pathname: "/", search: "", href: "http://localhost/" },
      writable: true,
      configurable: true,
    });

    const tracker = createTracker(makeConfig());
    tracker.pageview();

    expect(sentPayloads).toHaveLength(0);
  });
});

describe("domain filtering", () => {
  it("tracks on allowed domains", () => {
    const tracker = createTracker(makeConfig({ domains: ["example.com"] }));
    tracker.pageview();
    expect(sentPayloads).toHaveLength(1);
  });

  it("blocks on disallowed domains", () => {
    const tracker = createTracker(makeConfig({ domains: ["other.com"] }));
    tracker.pageview();
    expect(sentPayloads).toHaveLength(0);
  });

  it("allows subdomains", () => {
    Object.defineProperty(window, "location", {
      value: { hostname: "sub.example.com", pathname: "/", search: "" },
      writable: true,
      configurable: true,
    });

    const tracker = createTracker(makeConfig({ domains: ["example.com"] }));
    tracker.pageview();
    expect(sentPayloads).toHaveLength(1);
  });
});

describe("tag", () => {
  it("includes tag in payload when configured", () => {
    const tracker = createTracker(makeConfig({ tag: "production" }));
    tracker.pageview();

    const payload = lastPayload();
    expect(payload.payload.tag).toBe("production");
  });

  it("omits tag when not configured", () => {
    const tracker = createTracker(makeConfig());
    tracker.pageview();

    const payload = lastPayload();
    expect(payload.payload.tag).toBeUndefined();
  });
});

describe("custom hostname", () => {
  it("uses custom hostname when configured", () => {
    const tracker = createTracker(makeConfig({ hostname: "custom.example.com" }));
    tracker.pageview();

    const payload = lastPayload();
    expect(payload.payload.hostname).toBe("custom.example.com");
  });
});
