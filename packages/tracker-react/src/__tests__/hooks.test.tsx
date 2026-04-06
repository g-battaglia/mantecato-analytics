import { describe, it, expect, vi } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { TrackerProvider } from "../TrackerProvider";
import { useTracker } from "../useTracker";
import { usePageview } from "../usePageview";

// Stub sendBeacon and fetch so no network calls go out
Object.defineProperty(navigator, "sendBeacon", {
  value: vi.fn(() => false),
  writable: true,
  configurable: true,
});
vi.stubGlobal("fetch", vi.fn(async () => new Response("ok")));

// Stub location for non-localhost tracking
Object.defineProperty(window, "location", {
  value: { hostname: "example.com", pathname: "/test", search: "", href: "https://example.com/test" },
  writable: true,
  configurable: true,
});

Object.defineProperty(navigator, "userAgent", {
  value: "Mozilla/5.0 Test",
  writable: true,
  configurable: true,
});

const defaultProps = {
  websiteId: "test-id",
  baseUrl: "https://analytics.test.com",
  autoTrack: false,
};

describe("TrackerProvider", () => {
  it("renders children", () => {
    render(
      <TrackerProvider {...defaultProps}>
        <div data-testid="child">hello</div>
      </TrackerProvider>,
    );
    expect(screen.getByTestId("child")).toBeTruthy();
  });
});

describe("useTracker", () => {
  it("throws outside of TrackerProvider", () => {
    function Bad() {
      useTracker();
      return null;
    }

    // Suppress React error boundary noise
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Bad />)).toThrow("useTracker must be used within a <TrackerProvider>");
    spy.mockRestore();
  });

  it("returns a tracker instance inside provider", () => {
    let tracker: ReturnType<typeof useTracker> | null = null;

    function Consumer() {
      tracker = useTracker();
      return null;
    }

    render(
      <TrackerProvider {...defaultProps}>
        <Consumer />
      </TrackerProvider>,
    );

    expect(tracker).not.toBeNull();
    expect(tracker!.pageview).toBeTypeOf("function");
    expect(tracker!.event).toBeTypeOf("function");
    expect(tracker!.revenue).toBeTypeOf("function");
    expect(tracker!.identify).toBeTypeOf("function");
  });
});

describe("usePageview", () => {
  it("calls tracker.pageview on mount", () => {
    const pageviewSpy = vi.fn();

    // Use a spy tracker via useTracker
    function Page() {
      const tracker = useTracker();
      // Patch the tracker's pageview for spying
      if (!(tracker as Record<string, unknown>).__patched) {
        const original = tracker.pageview;
        tracker.pageview = (...args) => {
          pageviewSpy(...args);
          original.call(tracker, ...args);
        };
        (tracker as Record<string, unknown>).__patched = true;
      }
      usePageview("/my-page");
      return <div>page</div>;
    }

    render(
      <TrackerProvider {...defaultProps}>
        <Page />
      </TrackerProvider>,
    );

    expect(pageviewSpy).toHaveBeenCalledTimes(1);
    expect(pageviewSpy).toHaveBeenCalledWith({ url: "/my-page", title: undefined });
  });
});
