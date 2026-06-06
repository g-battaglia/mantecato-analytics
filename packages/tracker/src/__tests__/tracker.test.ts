import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createTracker, type Tracker, type TrackerConfig } from "../tracker";

// Capture all fetch calls
let sentPayloads: Array<{ url: string; body: string; headers: Record<string, string> }> = [];

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

function lastHeaders() {
  const last = sentPayloads[sentPayloads.length - 1];
  if (!last) throw new Error("No payload sent");
  return last.headers;
}

beforeEach(() => {
  sentPayloads = [];

  // Override fetch to capture payloads and return Umami-compatible response
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const headers: Record<string, string> = {};
      if (init?.headers) {
        for (const [k, v] of Object.entries(init.headers as Record<string, string>)) {
          headers[k] = v;
        }
      }
      sentPayloads.push({ url, body: (init?.body as string) || "", headers });
      return new Response(JSON.stringify({ cache: "test-cache-token" }), {
        headers: { "Content-Type": "application/json" },
      });
    }),
  );

  // Reset location and userAgent
  Object.defineProperty(window, "location", {
    value: {
      hostname: "example.com",
      pathname: "/page",
      search: "",
      hash: "",
      href: "https://example.com/page",
      origin: "https://example.com",
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

  // Reset window.doNotTrack (tests that set it pollute global state)
  Object.defineProperty(window, "doNotTrack", {
    value: undefined,
    writable: true,
    configurable: true,
  });

  // Mock localStorage
  const store: Record<string, string> = {};
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { for (const k in store) delete store[k]; },
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
    expect(tracker.track).toBeTypeOf("function");
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
  it("sends a pageview with correct payload structure", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.pageview();

    const payload = lastPayload();
    expect(payload.type).toBe("event");
    expect(payload.payload.website).toBe("test-site-id");
    // normalize() returns full absolute URL like Umami
    expect(payload.payload.url).toBe("https://example.com/page");
    expect(payload.payload.hostname).toBe("example.com");
    expect(payload.payload.language).toBe("en-US");
    expect(payload.payload.title).toBe("Test Page");
  });

  it("allows overriding url, title, referrer", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.pageview({ url: "/custom", title: "Custom", referrer: "https://google.com" });

    const payload = lastPayload();
    expect(payload.payload.url).toBe("https://example.com/custom");
    expect(payload.payload.title).toBe("Custom");
    expect(payload.payload.referrer).toBe("https://google.com");
  });

  it("sends to correct API endpoint", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.pageview();

    expect(sentPayloads[0].url).toBe("https://analytics.example.com/api/send");
  });

  it("uses custom endpoint when configured", async () => {
    const tracker = createTracker(makeConfig({ endpoint: "/custom/track" }));
    await tracker.pageview();

    expect(sentPayloads[0].url).toBe("https://analytics.example.com/custom/track");
  });

  it("sends credentials: omit on fetch", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.pageview();

    const fetchCall = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(fetchCall[1].credentials).toBe("omit");
  });
});

describe("event", () => {
  it("sends a custom event", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.event("signup", { plan: "pro" });

    const payload = lastPayload();
    expect(payload.type).toBe("event");
    expect(payload.payload.name).toBe("signup");
    expect(payload.payload.data).toEqual({ plan: "pro" });
  });

  it("sends event without data", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.event("click");

    const payload = lastPayload();
    expect(payload.payload.name).toBe("click");
    expect(payload.payload.data).toBeUndefined();
  });
});

describe("revenue", () => {
  it("sends a revenue event with amount and currency", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.revenue(29.99, "USD");

    const payload = lastPayload();
    expect(payload.payload.name).toBe("revenue");
    expect(payload.payload.revenue).toEqual({ amount: 29.99, currency: "USD" });
  });

  it("includes extra data with revenue event", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.revenue(100, "EUR", { product: "widget" });

    const payload = lastPayload();
    expect(payload.payload.revenue).toEqual({ amount: 100, currency: "EUR" });
    expect(payload.payload.data).toEqual({ product: "widget" });
  });
});

describe("identify", () => {
  it("sends type: identify (not event)", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.identify({ userId: "abc123" });

    const payload = lastPayload();
    expect(payload.type).toBe("identify");
    expect(payload.payload.data).toEqual({ userId: "abc123" });
  });

  it("supports (id, data) signature like Umami", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.identify("user-42", { plan: "enterprise" });

    const payload = lastPayload();
    expect(payload.type).toBe("identify");
    expect(payload.payload.id).toBe("user-42");
    expect(payload.payload.data).toEqual({ plan: "enterprise" });
  });

  it("persists id across subsequent calls", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.identify("user-42");
    await tracker.pageview();

    const pvPayload = JSON.parse(sentPayloads[1].body);
    expect(pvPayload.payload.id).toBe("user-42");
  });

  it("clears cache on identify", async () => {
    const tracker = createTracker(makeConfig());
    // First call sets cache
    await tracker.pageview();
    // identify should clear cache
    await tracker.identify("user-42");

    // The identify call should NOT have x-umami-cache header
    const identifyHeaders = sentPayloads[1].headers;
    expect(identifyHeaders["x-umami-cache"]).toBeUndefined();
  });
});

describe("cache token (x-umami-cache)", () => {
  it("sends x-umami-cache header after receiving cache from server", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.pageview();

    // Second call should include the cache header
    await tracker.pageview();

    const headers = sentPayloads[1].headers;
    expect(headers["x-umami-cache"]).toBe("test-cache-token");
  });
});

describe("server disabled flag", () => {
  it("stops tracking when server returns disabled: true", async () => {
    // Override fetch to return disabled flag
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const headers: Record<string, string> = {};
        if (init?.headers) {
          for (const [k, v] of Object.entries(init.headers as Record<string, string>)) {
            headers[k] = v;
          }
        }
        sentPayloads.push({ url, body: (init?.body as string) || "", headers });
        return new Response(JSON.stringify({ disabled: true }), {
          headers: { "Content-Type": "application/json" },
        });
      }),
    );

    const tracker = createTracker(makeConfig());
    await tracker.pageview();
    expect(sentPayloads).toHaveLength(1);

    // After disabled response, subsequent calls should be suppressed
    await tracker.pageview();
    expect(sentPayloads).toHaveLength(1);
  });
});

describe("enable/disable", () => {
  it("stops sending when disabled", async () => {
    const tracker = createTracker(makeConfig());
    tracker.disable();
    await tracker.pageview();

    expect(sentPayloads).toHaveLength(0);
  });

  it("resumes sending when re-enabled", async () => {
    const tracker = createTracker(makeConfig());
    tracker.disable();
    await tracker.pageview();
    expect(sentPayloads).toHaveLength(0);

    tracker.enable();
    await tracker.pageview();
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

describe("localStorage umami.disabled", () => {
  it("does not track when umami.disabled is set", async () => {
    localStorage.setItem("umami.disabled", "1");
    const tracker = createTracker(makeConfig());
    await tracker.pageview();

    expect(sentPayloads).toHaveLength(0);
  });
});

describe("empty websiteId", () => {
  it("does not track when websiteId is empty", async () => {
    const tracker = createTracker(makeConfig({ websiteId: "" }));
    await tracker.pageview();
    expect(sentPayloads).toHaveLength(0);
  });
});

describe("destroy", () => {
  it("disables tracking on destroy", async () => {
    const tracker = createTracker(makeConfig());
    tracker.destroy();
    expect(tracker.isEnabled()).toBe(false);
    await tracker.pageview();
    expect(sentPayloads).toHaveLength(0);
  });
});

describe("DNT", () => {
  it("respects navigator.doNotTrack = 1", async () => {
    Object.defineProperty(navigator, "doNotTrack", {
      value: "1",
      writable: true,
      configurable: true,
    });

    const tracker = createTracker(makeConfig({ respectDNT: true }));
    await tracker.pageview();

    expect(sentPayloads).toHaveLength(0);
  });

  it("respects window.doNotTrack", async () => {
    Object.defineProperty(window, "doNotTrack", {
      value: "1",
      writable: true,
      configurable: true,
    });

    const tracker = createTracker(makeConfig({ respectDNT: true }));
    await tracker.pageview();

    expect(sentPayloads).toHaveLength(0);
  });

  it("ignores DNT when respectDNT is false", async () => {
    Object.defineProperty(navigator, "doNotTrack", {
      value: "1",
      writable: true,
      configurable: true,
    });

    const tracker = createTracker(makeConfig({ respectDNT: false }));
    await tracker.pageview();

    expect(sentPayloads).toHaveLength(1);
  });
});

describe("bot detection", () => {
  it("does not track bots", async () => {
    Object.defineProperty(navigator, "userAgent", {
      value: "Googlebot/2.1",
      writable: true,
      configurable: true,
    });

    const tracker = createTracker(makeConfig());
    await tracker.pageview();

    expect(sentPayloads).toHaveLength(0);
  });
});

describe("localhost filtering", () => {
  it("does not track on localhost", async () => {
    Object.defineProperty(window, "location", {
      value: { hostname: "localhost", pathname: "/", search: "", hash: "", href: "http://localhost/", origin: "http://localhost" },
      writable: true,
      configurable: true,
    });

    const tracker = createTracker(makeConfig());
    await tracker.pageview();

    expect(sentPayloads).toHaveLength(0);
  });
});

describe("domain filtering", () => {
  it("tracks on allowed domains (exact match)", async () => {
    const tracker = createTracker(makeConfig({ domains: ["example.com"] }));
    await tracker.pageview();
    expect(sentPayloads).toHaveLength(1);
  });

  it("blocks on disallowed domains", async () => {
    const tracker = createTracker(makeConfig({ domains: ["other.com"] }));
    await tracker.pageview();
    expect(sentPayloads).toHaveLength(0);
  });

  it("blocks subdomains (exact match like Umami)", async () => {
    Object.defineProperty(window, "location", {
      value: { hostname: "sub.example.com", pathname: "/", search: "", hash: "", href: "https://sub.example.com/", origin: "https://sub.example.com" },
      writable: true,
      configurable: true,
    });

    const tracker = createTracker(makeConfig({ domains: ["example.com"] }));
    await tracker.pageview();
    expect(sentPayloads).toHaveLength(0);
  });
});

describe("tag", () => {
  it("includes tag in payload when configured", async () => {
    const tracker = createTracker(makeConfig({ tag: "production" }));
    await tracker.pageview();

    const payload = lastPayload();
    expect(payload.payload.tag).toBe("production");
  });

  it("omits tag when not configured", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.pageview();

    const payload = lastPayload();
    expect(payload.payload.tag).toBeUndefined();
  });
});

describe("custom hostname", () => {
  it("uses custom hostname when configured", async () => {
    const tracker = createTracker(makeConfig({ hostname: "custom.example.com" }));
    await tracker.pageview();

    const payload = lastPayload();
    expect(payload.payload.hostname).toBe("custom.example.com");
  });
});

describe("excludeSearch", () => {
  it("strips query string when excludeSearch is true", async () => {
    Object.defineProperty(window, "location", {
      value: {
        hostname: "example.com",
        pathname: "/page",
        search: "?foo=bar&baz=1",
        href: "https://example.com/page?foo=bar&baz=1",
        hash: "",
        origin: "https://example.com",
      },
      writable: true,
      configurable: true,
    });

    const tracker = createTracker(makeConfig({ excludeSearch: true }));
    await tracker.pageview();

    const payload = lastPayload();
    expect(payload.payload.url).toBe("https://example.com/page");
  });

  it("keeps query string when excludeSearch is false", async () => {
    Object.defineProperty(window, "location", {
      value: {
        hostname: "example.com",
        pathname: "/page",
        search: "?foo=bar",
        href: "https://example.com/page?foo=bar",
        hash: "",
        origin: "https://example.com",
      },
      writable: true,
      configurable: true,
    });

    const tracker = createTracker(makeConfig({ excludeSearch: false }));
    await tracker.pageview();

    const payload = lastPayload();
    expect(payload.payload.url).toBe("https://example.com/page?foo=bar");
  });
});

describe("excludeHash", () => {
  it("strips hash when excludeHash is true", async () => {
    Object.defineProperty(window, "location", {
      value: {
        hostname: "example.com",
        pathname: "/page",
        search: "",
        href: "https://example.com/page#section",
        hash: "#section",
        origin: "https://example.com",
      },
      writable: true,
      configurable: true,
    });

    const tracker = createTracker(makeConfig({ excludeHash: true }));
    await tracker.pageview();

    const payload = lastPayload();
    expect(payload.payload.url).toBe("https://example.com/page");
  });

  it("keeps hash when excludeHash is false", async () => {
    Object.defineProperty(window, "location", {
      value: {
        hostname: "example.com",
        pathname: "/page",
        search: "",
        href: "https://example.com/page#section",
        hash: "#section",
        origin: "https://example.com",
      },
      writable: true,
      configurable: true,
    });

    const tracker = createTracker(makeConfig({ excludeHash: false }));
    await tracker.pageview();

    const payload = lastPayload();
    expect(payload.payload.url).toBe("https://example.com/page#section");
  });
});

describe("excludeSearch + excludeHash combined", () => {
  it("strips both query and hash when both are true", async () => {
    Object.defineProperty(window, "location", {
      value: {
        hostname: "example.com",
        pathname: "/page",
        search: "?q=1",
        href: "https://example.com/page?q=1#top",
        hash: "#top",
        origin: "https://example.com",
      },
      writable: true,
      configurable: true,
    });

    const tracker = createTracker(makeConfig({ excludeSearch: true, excludeHash: true }));
    await tracker.pageview();

    const payload = lastPayload();
    expect(payload.payload.url).toBe("https://example.com/page");
  });
});

describe("beforeSend", () => {
  it("allows modifying payload before send", async () => {
    const tracker = createTracker(makeConfig({
      beforeSend: (_type, payload) => ({ ...payload, title: "Modified Title" }),
    }));
    await tracker.pageview();

    const payload = lastPayload();
    expect(payload.payload.title).toBe("Modified Title");
  });

  it("cancels send when beforeSend returns falsy", async () => {
    const tracker = createTracker(makeConfig({
      beforeSend: () => null,
    }));
    await tracker.pageview();

    expect(sentPayloads).toHaveLength(0);
  });

  it("supports async beforeSend", async () => {
    const tracker = createTracker(makeConfig({
      beforeSend: async (_type, payload) => {
        return { ...payload, title: "Async Modified" };
      },
    }));
    await tracker.pageview();

    const payload = lastPayload();
    expect(payload.payload.title).toBe("Async Modified");
  });

  it("receives correct type argument for events vs identify", async () => {
    const types: string[] = [];
    const tracker = createTracker(makeConfig({
      beforeSend: (type, payload) => { types.push(type); return payload; },
    }));
    await tracker.event("test");
    await tracker.identify({ user: "x" });

    expect(types).toEqual(["event", "identify"]);
  });
});

describe("credentials", () => {
  it("uses custom credentials when configured", async () => {
    const tracker = createTracker(makeConfig({ credentials: "include" }));
    await tracker.pageview();

    const fetchCall = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(fetchCall[1].credentials).toBe("include");
  });

  it("defaults to omit", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.pageview();

    const fetchCall = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(fetchCall[1].credentials).toBe("omit");
  });
});

describe("track() — Umami-compatible overloads", () => {
  it("track() with no args sends a pageview", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.track();

    const payload = lastPayload();
    expect(payload.type).toBe("event");
    expect(payload.payload.name).toBeUndefined();
    expect(payload.payload.url).toBe("https://example.com/page");
  });

  it("track(name) sends a named event", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.track("signup");

    const payload = lastPayload();
    expect(payload.payload.name).toBe("signup");
  });

  it("track(name, data) sends a named event with data", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.track("signup", { plan: "pro" });

    const payload = lastPayload();
    expect(payload.payload.name).toBe("signup");
    expect(payload.payload.data).toEqual({ plan: "pro" });
  });

  it("track(object) sends raw payload without defaults (like Umami)", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.track({ website: "other-site", url: "/custom-url", title: "Custom" } as any);

    const payload = lastPayload();
    // Umami sends the raw object, not merged with defaults
    expect(payload.payload.website).toBe("other-site");
    expect(payload.payload.url).toBe("/custom-url");
    expect(payload.payload.title).toBe("Custom");
    // Default fields should NOT be present
    expect(payload.payload.hostname).toBeUndefined();
    expect(payload.payload.language).toBeUndefined();
  });

  it("track(function) sends result of callback with defaults as input", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.track((props) => ({ ...props, name: "dynamic", url: "/modified" }));

    const payload = lastPayload();
    expect(payload.payload.name).toBe("dynamic");
    expect(payload.payload.url).toBe("/modified");
    // Defaults should be present since callback receives them
    expect(payload.payload.hostname).toBe("example.com");
  });
});
