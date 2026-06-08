import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createTracker, type TrackerConfig } from "../tracker";

let sentPayloads: Array<{ url: string; body: string; headers: Record<string, string> }>;

function makeConfig(overrides: Partial<TrackerConfig> = {}): TrackerConfig {
  return {
    websiteId: "test-site-id",
    baseUrl: "https://analytics.example.com",
    autoTrack: false,
    ...overrides,
  };
}

function lastPayload() {
  const last = sentPayloads.at(-1);
  if (!last) throw new Error("No payload sent");
  return JSON.parse(last.body);
}

beforeEach(() => {
  sentPayloads = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const headers: Record<string, string> = {};
      if (init?.headers) {
        Object.assign(headers, init.headers as Record<string, string>);
      }
      sentPayloads.push({ url, body: (init?.body as string) || "", headers });
      return new Response(JSON.stringify({ ok: true }), {
        headers: { "Content-Type": "application/json" },
      });
    }),
  );

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
  Object.defineProperty(window, "doNotTrack", {
    value: undefined,
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
  it("exposes only privacy-first methods", () => {
    const tracker = createTracker(makeConfig()) as unknown as Record<string, unknown>;
    expect(tracker.pageview).toBeTypeOf("function");
    expect(tracker.event).toBeTypeOf("function");
    expect(tracker.track).toBeTypeOf("function");
    expect(tracker.enable).toBeTypeOf("function");
    expect(tracker.disable).toBeTypeOf("function");
    expect(tracker.isEnabled).toBeTypeOf("function");
    expect(tracker.destroy).toBeTypeOf("function");
    expect(tracker.identify).toBeUndefined();
    expect(tracker.revenue).toBeUndefined();
    expect(tracker.send).toBeUndefined();
  });
});

describe("pageview", () => {
  it("sends only allowed anonymous pageview fields", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.pageview();

    const payload = lastPayload();
    expect(payload).toEqual({
      type: "event",
      payload: {
        website: "test-site-id",
        hostname: "example.com",
        title: "Test Page",
        url: "https://example.com/page",
      },
    });
  });

  it("overrides url and title; omits empty referrer and never sends language", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.pageview({ url: "/custom", title: "Custom" });

    const payload = lastPayload();
    expect(payload.payload.url).toBe("https://example.com/custom");
    expect(payload.payload.title).toBe("Custom");
    expect(payload.payload.referrer).toBeUndefined();
    expect(payload.payload.language).toBeUndefined();
  });

  it("includes the referrer when the document has one (domain reduced server-side)", async () => {
    Object.defineProperty(document, "referrer", {
      value: "https://news.example.org/article?x=1",
      writable: true,
      configurable: true,
    });
    const tracker = createTracker(makeConfig());
    await tracker.pageview();

    const payload = lastPayload();
    expect(payload.payload.referrer).toBe("https://news.example.org/article?x=1");
  });
});

describe("event", () => {
  it("sends a custom event name without properties", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.event("signup", { url: "/signup", title: "Signup" });

    const payload = lastPayload();
    expect(payload.payload.name).toBe("signup");
    expect(payload.payload.url).toBe("https://example.com/signup");
    expect(payload.payload.title).toBe("Signup");
    expect(payload.payload.data).toBeUndefined();
    expect(payload.payload.revenue).toBeUndefined();
  });

  it("supports track(name) as an event alias", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.track("cta_click");

    expect(lastPayload().payload.name).toBe("cta_click");
  });

  it("sanitizes raw track objects", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.track({
      website: "other-site",
      url: "/custom-url",
      title: "Custom",
      name: "raw",
      data: { plan: "pro" },
    } as never);

    const payload = lastPayload();
    expect(payload.payload.website).toBe("test-site-id");
    expect(payload.payload.url).toBe("https://example.com/custom-url");
    expect(payload.payload.name).toBe("raw");
    expect(payload.payload.data).toBeUndefined();
  });
});

describe("controls", () => {
  it("sends to the configured endpoint with credentials omitted by default", async () => {
    const tracker = createTracker(makeConfig());
    await tracker.pageview();

    const call = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(sentPayloads[0].url).toBe("https://analytics.example.com/api/send");
    expect(call[1].credentials).toBe("omit");
  });

  it("stops and resumes with disable/enable", async () => {
    const tracker = createTracker(makeConfig());
    tracker.disable();
    await tracker.pageview();
    expect(sentPayloads).toHaveLength(0);

    tracker.enable();
    await tracker.pageview();
    expect(sentPayloads).toHaveLength(1);
  });

  it("respects DNT when enabled", async () => {
    Object.defineProperty(navigator, "doNotTrack", {
      value: "1",
      writable: true,
      configurable: true,
    });
    const tracker = createTracker(makeConfig({ respectDNT: true }));
    await tracker.pageview();
    expect(sentPayloads).toHaveLength(0);
  });

  it("does not track known bots", async () => {
    Object.defineProperty(navigator, "userAgent", {
      value: "Googlebot/2.1",
      writable: true,
      configurable: true,
    });
    const tracker = createTracker(makeConfig());
    await tracker.pageview();
    expect(sentPayloads).toHaveLength(0);
  });

  it("honors exact domain allow-listing", async () => {
    const tracker = createTracker(makeConfig({ domains: ["other.com"] }));
    await tracker.pageview();
    expect(sentPayloads).toHaveLength(0);
  });
});

describe("beforeSend", () => {
  it("can cancel sends and only sees event payloads", async () => {
    const types: string[] = [];
    const tracker = createTracker(makeConfig({
      beforeSend: (type) => {
        types.push(type);
        return false;
      },
    }));
    await tracker.event("blocked");

    expect(types).toEqual(["event"]);
    expect(sentPayloads).toHaveLength(0);
  });
});
