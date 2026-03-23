#!/usr/bin/env node
/**
 * Mantecato MCP Server — expose all analytics as MCP tools.
 *
 * Usage:
 *   npx tsx src/mcp/server.ts              # stdio transport
 *   MANTECATO_MCP=1 npx tsx src/mcp/server.ts
 *
 * OpenCode config (~/.config/opencode/config.json):
 *   {
 *     "mcpServers": {
 *       "mantecato": {
 *         "command": "npx",
 *         "args": ["tsx", "/path/to/mantecato-analytics/src/mcp/server.ts"],
 *         "env": { "DATABASE_URL": "..." }
 *       }
 *     }
 *   }
 */
import "dotenv/config";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

import {
  listSites,
  resolveSiteId,
  parseDateArgs,
  resolveGranularityArg,
  parseFilterArgs,
  computeDerivedStats,
} from "../cli/helpers.js";

import { getWebsiteStats, getPageviewTimeSeries, getTopPages, getTopReferrers, getTopEvents } from "@/queries/stats";
import { getPageMetrics, getPageReferrers, getNextPages, getTimeOnPageDistribution, getPageTimeSeries } from "@/queries/pageviews";
import { getReferrerMetrics, getUTMDetailMetrics, getChannelMetrics, getClickIdMetrics, getHostnameMetrics, getReferrerPages } from "@/queries/sources";
import { getEventMetrics, getEventTimeSeries, getEventProperties } from "@/queries/events";
import { getSessionList, getSessionActivity } from "@/queries/sessions";
import { getDeviceMetrics } from "@/queries/devices";
import { getGeoMetrics } from "@/queries/geo";
import { getActiveVisitors, getRecentEvents, getCurrentPages } from "@/queries/realtime";
import { getComparisonStats } from "@/queries/compare";
import { getRetention } from "@/queries/retention";
import { getFunnel } from "@/queries/funnels";
import { getJourneys } from "@/queries/journeys";
import { getRevenueSummary, getRevenueTimeSeries, getRevenueByEvent, getRevenueByCountry } from "@/queries/revenue";
import { getDurationDistribution, getDurationPercentiles, getDurationByPage, getBounceRateByPage, getBounceRateBySource } from "@/queries/engagement";
import { getFilterValues } from "@/queries/filter-values";
import { getComparisonRange } from "@/lib/date";

// ---------------------------------------------------------------------------
// Helper to build tool results
// ---------------------------------------------------------------------------

function ok(data: unknown): { content: Array<{ type: "text"; text: string }> } {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }],
  };
}

function err(message: string): { content: Array<{ type: "text"; text: string }>; isError: true } {
  return {
    content: [{ type: "text" as const, text: `Error: ${message}` }],
    isError: true as const,
  };
}

// Common params used by most tools
const siteParam = z.string().describe("Site name, domain, or UUID");
const periodParam = z.string().optional().default("30d").describe("Date range preset: 1h, 3h, 6h, today, yesterday, 24h, 7d, 14d, 30d, 60d, 90d, 6m, 12m, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, all");
const startParam = z.string().optional().describe("Custom start date (ISO 8601). Overrides period if set.");
const endParam = z.string().optional().describe("Custom end date (ISO 8601)");
const limitParam = z.number().optional().default(20).describe("Maximum rows to return");
const filtersParam = z.array(z.string()).optional().default([]).describe("Filters as column:operator:value strings. Operators: eq, neq, contains, not_contains, starts_with, not_starts_with. Example: ['country:eq:US', 'browser:eq:chrome']");
const granularityParam = z.string().optional().default("auto").describe("Time granularity: auto, minute, hour, day, week, month");

// ---------------------------------------------------------------------------
// Server setup
// ---------------------------------------------------------------------------

const server = new McpServer({
  name: "mantecato",
  version: "0.1.0",
});

// --- list_sites ---
server.tool(
  "list_sites",
  "List all tracked websites with their IDs, names, and domains",
  {},
  async () => {
    try {
      return ok(await listSites());
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_stats ---
server.tool(
  "get_stats",
  "Get overview stats for a site: pageviews, visitors, visits, bounce rate, avg duration, pages/visit",
  {
    site: siteParam,
    period: periodParam,
    start: startParam,
    end: endParam,
    filters: filtersParam,
  },
  async ({ site, period, start, end, filters }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const f = parseFilterArgs(filters);
      const raw = await getWebsiteStats(siteId, range.startDate, range.endDate, f);
      return ok(computeDerivedStats(raw));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_timeseries ---
server.tool(
  "get_timeseries",
  "Get pageview and visitor time series data",
  {
    site: siteParam,
    period: periodParam,
    start: startParam,
    end: endParam,
    granularity: granularityParam,
    filters: filtersParam,
  },
  async ({ site, period, start, end, granularity, filters }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const gran = resolveGranularityArg(granularity, range);
      const f = parseFilterArgs(filters);
      return ok(await getPageviewTimeSeries(siteId, range.startDate, range.endDate, gran, f));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_pages ---
server.tool(
  "get_pages",
  "Get page analytics: views, visitors, time-on-page, bounce rate, entries, exits",
  {
    site: siteParam,
    period: periodParam,
    start: startParam,
    end: endParam,
    limit: limitParam,
    filters: filtersParam,
    mode: z.enum(["path", "slug"]).optional().default("path").describe("Grouping mode: path (exact) or slug (normalized, strips query strings/trailing slashes)"),
  },
  async ({ site, period, start, end, limit, filters, mode }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const f = parseFilterArgs(filters);
      return ok(await getPageMetrics(siteId, range.startDate, range.endDate, limit, 0, f, mode));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_page_detail ---
server.tool(
  "get_page_detail",
  "Get detailed analytics for a specific page: referrers, next pages, time-on-page distribution, time series",
  {
    site: siteParam,
    url: z.string().describe("URL path to analyze, e.g. /pricing"),
    period: periodParam,
    start: startParam,
    end: endParam,
    granularity: granularityParam,
    limit: limitParam,
  },
  async ({ site, url, period, start, end, granularity, limit }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const gran = resolveGranularityArg(granularity, range);
      const [referrers, nextPages, distribution, timeseries] = await Promise.all([
        getPageReferrers(siteId, url, range.startDate, range.endDate, limit),
        getNextPages(siteId, url, range.startDate, range.endDate, limit),
        getTimeOnPageDistribution(siteId, url, range.startDate, range.endDate),
        getPageTimeSeries(siteId, url, range.startDate, range.endDate, gran),
      ]);
      return ok({ referrers, nextPages, distribution, timeseries });
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_sources ---
server.tool(
  "get_sources",
  "Get traffic sources/referrers with bounce rate and avg duration",
  {
    site: siteParam,
    period: periodParam,
    start: startParam,
    end: endParam,
    limit: limitParam,
    filters: filtersParam,
  },
  async ({ site, period, start, end, limit, filters }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const f = parseFilterArgs(filters);
      return ok(await getReferrerMetrics(siteId, range.startDate, range.endDate, limit, f));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_referrer_pages ---
server.tool(
  "get_referrer_pages",
  "Drill-down: which pages a specific referrer drives traffic to",
  {
    site: siteParam,
    referrer: z.string().describe("Referrer domain to drill down, e.g. google.com or (direct)"),
    period: periodParam,
    start: startParam,
    end: endParam,
    limit: limitParam,
    filters: filtersParam,
  },
  async ({ site, referrer, period, start, end, limit, filters }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const f = parseFilterArgs(filters);
      return ok(await getReferrerPages(siteId, range.startDate, range.endDate, referrer, limit, f));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_channels ---
server.tool(
  "get_channels",
  "Get auto-grouped traffic channels: Organic Search, Direct, Paid Search, Social, Email, Referral, etc.",
  {
    site: siteParam,
    period: periodParam,
    start: startParam,
    end: endParam,
    filters: filtersParam,
  },
  async ({ site, period, start, end, filters }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const f = parseFilterArgs(filters);
      return ok(await getChannelMetrics(siteId, range.startDate, range.endDate, f));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_utm ---
server.tool(
  "get_utm",
  "Get UTM parameter breakdown by a specific dimension",
  {
    site: siteParam,
    dimension: z.enum(["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"]).optional().default("utm_source").describe("UTM dimension to group by"),
    period: periodParam,
    start: startParam,
    end: endParam,
    limit: limitParam,
    filters: filtersParam,
  },
  async ({ site, dimension, period, start, end, limit, filters }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const f = parseFilterArgs(filters);
      return ok(await getUTMDetailMetrics(siteId, range.startDate, range.endDate, dimension, limit, f));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_click_ids ---
server.tool(
  "get_click_ids",
  "Get click ID analysis: gclid (Google Ads), fbclid (Facebook), msclkid (Microsoft), etc.",
  {
    site: siteParam,
    period: periodParam,
    start: startParam,
    end: endParam,
    filters: filtersParam,
  },
  async ({ site, period, start, end, filters }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const f = parseFilterArgs(filters);
      return ok(await getClickIdMetrics(siteId, range.startDate, range.endDate, f));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_hostnames ---
server.tool(
  "get_hostnames",
  "Get hostname/subdomain breakdown for multi-domain tracking",
  {
    site: siteParam,
    period: periodParam,
    start: startParam,
    end: endParam,
    limit: limitParam,
    filters: filtersParam,
  },
  async ({ site, period, start, end, limit, filters }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const f = parseFilterArgs(filters);
      return ok(await getHostnameMetrics(siteId, range.startDate, range.endDate, limit, f));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_events ---
server.tool(
  "get_events",
  "Get custom event metrics: event names, counts, unique visitors, last triggered time",
  {
    site: siteParam,
    period: periodParam,
    start: startParam,
    end: endParam,
    limit: limitParam,
    filters: filtersParam,
  },
  async ({ site, period, start, end, limit, filters }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const f = parseFilterArgs(filters);
      return ok(await getEventMetrics(siteId, range.startDate, range.endDate, limit, f));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_event_detail ---
server.tool(
  "get_event_detail",
  "Get detailed analytics for a specific event: time series and custom properties",
  {
    site: siteParam,
    event: z.string().describe("Event name to analyze"),
    period: periodParam,
    start: startParam,
    end: endParam,
    granularity: granularityParam,
    limit: limitParam,
    filters: filtersParam,
  },
  async ({ site, event, period, start, end, granularity, limit, filters }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const gran = resolveGranularityArg(granularity, range);
      const f = parseFilterArgs(filters);
      const [timeseries, properties] = await Promise.all([
        getEventTimeSeries(siteId, event, range.startDate, range.endDate, gran, f),
        getEventProperties(siteId, event, range.startDate, range.endDate, limit),
      ]);
      return ok({ timeseries, properties });
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_sessions ---
server.tool(
  "get_sessions",
  "Get session list with country, device, browser, pages viewed, duration. Optionally filter by visited page or triggered event.",
  {
    site: siteParam,
    period: periodParam,
    start: startParam,
    end: endParam,
    limit: limitParam,
    filters: filtersParam,
    visitedPage: z.string().optional().describe("Filter to sessions that visited a specific URL path"),
    triggeredEvent: z.string().optional().describe("Filter to sessions that triggered a specific custom event"),
  },
  async ({ site, period, start, end, limit, filters, visitedPage, triggeredEvent }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const f = parseFilterArgs(filters);
      return ok(await getSessionList(siteId, range.startDate, range.endDate, limit, 0, f, visitedPage, triggeredEvent));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_session_activity ---
server.tool(
  "get_session_activity",
  "Get full event replay for a specific session: every pageview, custom event, and event properties in chronological order",
  {
    site: siteParam,
    sessionId: z.string().describe("Session UUID (from get_sessions results)"),
  },
  async ({ site, sessionId }) => {
    try {
      const siteId = await resolveSiteId(site);
      return ok(await getSessionActivity(sessionId, siteId));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_devices ---
server.tool(
  "get_devices",
  "Get device/browser/OS/screen/language breakdown with visitor counts and percentages",
  {
    site: siteParam,
    dimension: z.enum(["browser", "os", "device", "screen", "language"]).optional().default("device").describe("Dimension to break down by"),
    period: periodParam,
    start: startParam,
    end: endParam,
    limit: limitParam,
    filters: filtersParam,
  },
  async ({ site, dimension, period, start, end, limit, filters }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const f = parseFilterArgs(filters);
      return ok(await getDeviceMetrics(siteId, range.startDate, range.endDate, dimension, limit, f));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_geo ---
server.tool(
  "get_geo",
  "Get geographic breakdown of visitors: by country, region, or city. Supports drill-down with country/region filters.",
  {
    site: siteParam,
    level: z.enum(["country", "region", "city"]).optional().default("country").describe("Geographic level"),
    country: z.string().optional().describe("Filter by country code for region/city drill-down (e.g. US, IT)"),
    region: z.string().optional().describe("Filter by region name for city drill-down"),
    period: periodParam,
    start: startParam,
    end: endParam,
    limit: limitParam,
    filters: filtersParam,
  },
  async ({ site, level, country, region, period, start, end, limit, filters }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const f = parseFilterArgs(filters);
      return ok(await getGeoMetrics(siteId, range.startDate, range.endDate, level, country, region, limit, f));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_realtime ---
server.tool(
  "get_realtime",
  "Get real-time data: active visitors count, their current pages, and a stream of recent events (last 30 seconds)",
  {
    site: siteParam,
  },
  async ({ site }) => {
    try {
      const siteId = await resolveSiteId(site);
      const [active, pages, events] = await Promise.all([
        getActiveVisitors(siteId),
        getCurrentPages(siteId),
        getRecentEvents(siteId),
      ]);
      return ok({ activeVisitors: active.count, visitors: active.visitors, currentPages: pages, recentEvents: events });
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_comparison ---
server.tool(
  "get_comparison",
  "Compare current period stats vs previous period or previous year",
  {
    site: siteParam,
    period: periodParam,
    start: startParam,
    end: endParam,
    mode: z.enum(["previous_period", "previous_year"]).optional().default("previous_period").describe("Comparison mode"),
  },
  async ({ site, period, start, end, mode }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const prevRange = getComparisonRange(range, mode);
      const data = await getComparisonStats(siteId, range.startDate, range.endDate, prevRange.startDate, prevRange.endDate);
      const current = data.find((d) => d.period === "current");
      const previous = data.find((d) => d.period === "previous");
      return ok({
        current: current ? computeDerivedStats(current) : null,
        previous: previous ? computeDerivedStats(previous) : null,
        currentRange: { start: range.startDate.toISOString(), end: range.endDate.toISOString() },
        previousRange: { start: prevRange.startDate.toISOString(), end: prevRange.endDate.toISOString() },
      });
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_retention ---
server.tool(
  "get_retention",
  "Get cohort retention analysis: what percentage of visitors return in subsequent weeks/months",
  {
    site: siteParam,
    period: periodParam,
    start: startParam,
    end: endParam,
    granularity: z.enum(["week", "month"]).optional().default("week").describe("Cohort granularity"),
  },
  async ({ site, period, start, end, granularity }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      return ok(await getRetention(siteId, range.startDate, range.endDate, granularity));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- run_funnel ---
server.tool(
  "run_funnel",
  "Run funnel analysis: define steps (URLs or events) and see conversion rates at each step",
  {
    site: siteParam,
    steps: z.array(z.object({
      type: z.enum(["url", "event"]).describe("Step type"),
      value: z.string().describe("URL path or event name"),
    })).describe("Funnel steps (minimum 2). Example: [{type:'url',value:'/'},{type:'url',value:'/register'},{type:'event',value:'signup-complete'}]"),
    windowMinutes: z.number().optional().default(60).describe("Conversion window in minutes"),
    period: periodParam,
    start: startParam,
    end: endParam,
  },
  async ({ site, steps, windowMinutes, period, start, end }) => {
    try {
      if (steps.length < 2) return err("At least 2 funnel steps are required");
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      return ok(await getFunnel(siteId, range.startDate, range.endDate, steps, windowMinutes));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_journeys ---
server.tool(
  "get_journeys",
  "Get user journey paths: most common page sequences visitors follow through the site",
  {
    site: siteParam,
    pathLength: z.number().optional().default(3).describe("Number of steps in each path (default 3)"),
    period: periodParam,
    start: startParam,
    end: endParam,
    limit: limitParam,
  },
  async ({ site, pathLength, period, start, end, limit }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      return ok(await getJourneys(siteId, range.startDate, range.endDate, pathLength, limit));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_revenue ---
server.tool(
  "get_revenue",
  "Get revenue analytics: summary (total, transactions, ARPU), time series, by event, or by country",
  {
    site: siteParam,
    view: z.enum(["summary", "timeseries", "by-event", "by-country"]).optional().default("summary").describe("Which revenue view to return"),
    period: periodParam,
    start: startParam,
    end: endParam,
    granularity: granularityParam,
    limit: limitParam,
  },
  async ({ site, view, period, start, end, granularity, limit }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const gran = resolveGranularityArg(granularity, range);
      switch (view) {
        case "summary":
          return ok(await getRevenueSummary(siteId, range.startDate, range.endDate));
        case "timeseries":
          return ok(await getRevenueTimeSeries(siteId, range.startDate, range.endDate, gran));
        case "by-event":
          return ok(await getRevenueByEvent(siteId, range.startDate, range.endDate, limit));
        case "by-country":
          return ok(await getRevenueByCountry(siteId, range.startDate, range.endDate, limit));
      }
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_engagement ---
server.tool(
  "get_engagement",
  "Get engagement analytics: duration distribution, percentiles, time-on-page by page, bounce rates by entry page or by source",
  {
    site: siteParam,
    view: z.enum(["distribution", "percentiles", "by-page", "bounce-by-page", "bounce-by-source"]).optional().default("percentiles").describe("Which engagement view to return"),
    period: periodParam,
    start: startParam,
    end: endParam,
    limit: limitParam,
    filters: filtersParam,
  },
  async ({ site, view, period, start, end, limit, filters }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const f = parseFilterArgs(filters);
      switch (view) {
        case "distribution":
          return ok(await getDurationDistribution(siteId, range.startDate, range.endDate, f));
        case "percentiles":
          return ok(await getDurationPercentiles(siteId, range.startDate, range.endDate, f));
        case "by-page":
          return ok(await getDurationByPage(siteId, range.startDate, range.endDate, limit, f));
        case "bounce-by-page":
          return ok(await getBounceRateByPage(siteId, range.startDate, range.endDate, limit, f));
        case "bounce-by-source":
          return ok(await getBounceRateBySource(siteId, range.startDate, range.endDate, limit, f));
      }
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_filter_values ---
server.tool(
  "get_filter_values",
  "Get available values for a filter column (useful for autocomplete). Columns: url_path, page_title, hostname, referrer_domain, utm_source, utm_medium, utm_campaign, event_name, tag, browser, os, device, country, region, city, language, screen",
  {
    site: siteParam,
    column: z.string().describe("Column name to get values for"),
    period: periodParam,
    start: startParam,
    end: endParam,
    search: z.string().optional().describe("Search filter (ILIKE %search%)"),
    limit: limitParam,
  },
  async ({ site, column, period, start, end, search, limit }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      return ok(await getFilterValues(siteId, column, range.startDate, range.endDate, search, limit));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_top_pages ---
server.tool(
  "get_top_pages",
  "Quick: get top pages by visitors (lightweight version of get_pages)",
  {
    site: siteParam,
    period: periodParam,
    start: startParam,
    end: endParam,
    limit: limitParam,
    filters: filtersParam,
  },
  async ({ site, period, start, end, limit, filters }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const f = parseFilterArgs(filters);
      return ok(await getTopPages(siteId, range.startDate, range.endDate, limit, f));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_top_referrers ---
server.tool(
  "get_top_referrers",
  "Quick: get top referrers by visitors (lightweight version of get_sources)",
  {
    site: siteParam,
    period: periodParam,
    start: startParam,
    end: endParam,
    limit: limitParam,
    filters: filtersParam,
  },
  async ({ site, period, start, end, limit, filters }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const f = parseFilterArgs(filters);
      return ok(await getTopReferrers(siteId, range.startDate, range.endDate, limit, f));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- get_top_events ---
server.tool(
  "get_top_events",
  "Quick: get top custom events by count",
  {
    site: siteParam,
    period: periodParam,
    start: startParam,
    end: endParam,
    limit: limitParam,
    filters: filtersParam,
  },
  async ({ site, period, start, end, limit, filters }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      const f = parseFilterArgs(filters);
      return ok(await getTopEvents(siteId, range.startDate, range.endDate, limit, f));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// ---------------------------------------------------------------------------
// CRUD: Annotations, Saved Views, Dashboards, Scheduled Exports
// ---------------------------------------------------------------------------

import { listAnnotations, createAnnotation, deleteAnnotation } from "@/queries/annotations";
import { listSavedViews, getSavedView, createSavedView, deleteSavedView } from "@/queries/saved-views";
import { listDashboards, getDashboard, deleteDashboard } from "@/queries/dashboards";
import { listScheduledExports, getScheduledExport, deleteScheduledExport } from "@/queries/scheduled-exports";
import { validateApiKey } from "@/queries/api-keys";

// ---------------------------------------------------------------------------
// API Key authentication
// ---------------------------------------------------------------------------

let cachedUserId: string | null = null;

/**
 * Resolve userId from MANTECATO_API_KEY env var.
 * Caches the result after first validation.
 */
async function getMcpUserId(): Promise<string> {
  if (cachedUserId) return cachedUserId;

  const key = process.env.MANTECATO_API_KEY;
  if (!key) {
    throw new Error(
      "MANTECATO_API_KEY env var is required. " +
      "Generate a key in the Mantecato web UI: Settings > API Keys > New Key."
    );
  }

  const result = await validateApiKey(key);
  if (!result) {
    throw new Error("Invalid MANTECATO_API_KEY.");
  }

  cachedUserId = result.userId;
  return result.userId;
}

// --- annotations ---
server.tool(
  "list_annotations",
  "List timeline annotations for a site",
  {
    site: siteParam,
    period: periodParam,
    start: startParam,
    end: endParam,
  },
  async ({ site, period, start, end }) => {
    try {
      const siteId = await resolveSiteId(site);
      const range = parseDateArgs(period, start, end);
      return ok(await listAnnotations(await getMcpUserId(), siteId, range.startDate, range.endDate));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

server.tool(
  "create_annotation",
  "Create a timeline annotation on a site (e.g. 'Deployed v2.0', 'Started ad campaign')",
  {
    site: siteParam,
    title: z.string().describe("Annotation title"),
    date: z.string().describe("Date for the annotation (ISO 8601)"),
    description: z.string().optional().default("").describe("Annotation description"),
    color: z.enum(["blue", "green", "red", "amber", "purple"]).optional().default("blue").describe("Annotation color"),
  },
  async ({ site, title, date, description, color }) => {
    try {
      const siteId = await resolveSiteId(site);
      return ok(await createAnnotation(await getMcpUserId(), siteId, title, description, date, color));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

server.tool(
  "delete_annotation",
  "Delete an annotation by its report ID",
  {
    id: z.string().describe("Annotation report ID"),
  },
  async ({ id }) => {
    try {
      const deleted = await deleteAnnotation(id, await getMcpUserId());
      return ok({ deleted, message: deleted ? "Annotation deleted" : "Annotation not found or not owned by you" });
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- saved views ---
server.tool(
  "list_saved_views",
  "List saved views (filter + date presets) for a site",
  {
    site: siteParam,
  },
  async ({ site }) => {
    try {
      const siteId = await resolveSiteId(site);
      return ok(await listSavedViews(await getMcpUserId(), siteId));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

server.tool(
  "get_saved_view",
  "Get a specific saved view by ID",
  {
    id: z.string().describe("Saved view report ID"),
  },
  async ({ id }) => {
    try {
      const view = await getSavedView(id, await getMcpUserId());
      if (!view) return err("Saved view not found");
      return ok(view);
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

server.tool(
  "create_saved_view",
  "Create a saved view with filters and date preset",
  {
    site: siteParam,
    name: z.string().describe("View name"),
    description: z.string().optional().default("").describe("View description"),
    config: z.object({
      preset: z.string().describe("Date range preset (e.g. 30d)"),
      granularity: z.string().optional().default("auto"),
      filters: z.array(z.object({
        column: z.string(),
        operator: z.string(),
        value: z.string(),
      })).optional().default([]),
      page: z.string().optional().describe("Page this view applies to"),
    }).describe("View configuration"),
  },
  async ({ site, name, description, config }) => {
    try {
      const siteId = await resolveSiteId(site);
      return ok(await createSavedView(await getMcpUserId(), siteId, name, description, config));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

server.tool(
  "delete_saved_view",
  "Delete a saved view by ID",
  {
    id: z.string().describe("Saved view report ID"),
  },
  async ({ id }) => {
    try {
      const deleted = await deleteSavedView(id, await getMcpUserId());
      return ok({ deleted, message: deleted ? "Saved view deleted" : "Saved view not found" });
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- dashboards ---
server.tool(
  "list_dashboards",
  "List custom dashboards, optionally filtered by site",
  {
    site: z.string().optional().describe("Site name/domain/UUID to filter by (optional, returns all if omitted)"),
  },
  async ({ site }) => {
    try {
      const siteId = site ? await resolveSiteId(site) : undefined;
      return ok(await listDashboards(await getMcpUserId(), siteId));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

server.tool(
  "get_dashboard",
  "Get a specific custom dashboard by ID, including its widget configuration",
  {
    id: z.string().describe("Dashboard report ID"),
  },
  async ({ id }) => {
    try {
      const dashboard = await getDashboard(id, await getMcpUserId());
      if (!dashboard) return err("Dashboard not found");
      return ok(dashboard);
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

server.tool(
  "delete_dashboard",
  "Delete a custom dashboard by ID",
  {
    id: z.string().describe("Dashboard report ID"),
  },
  async ({ id }) => {
    try {
      const deleted = await deleteDashboard(id, await getMcpUserId());
      return ok({ deleted, message: deleted ? "Dashboard deleted" : "Dashboard not found" });
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// --- scheduled exports ---
server.tool(
  "list_scheduled_exports",
  "List all scheduled data exports",
  {},
  async () => {
    try {
      return ok(await listScheduledExports(await getMcpUserId()));
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

server.tool(
  "get_scheduled_export",
  "Get a specific scheduled export by ID",
  {
    id: z.string().describe("Scheduled export report ID"),
  },
  async ({ id }) => {
    try {
      const exp = await getScheduledExport(id, await getMcpUserId());
      if (!exp) return err("Scheduled export not found");
      return ok(exp);
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

server.tool(
  "delete_scheduled_export",
  "Delete a scheduled export by ID",
  {
    id: z.string().describe("Scheduled export report ID"),
  },
  async ({ id }) => {
    try {
      const deleted = await deleteScheduledExport(id, await getMcpUserId());
      return ok({ deleted, message: deleted ? "Scheduled export deleted" : "Scheduled export not found" });
    } catch (e: unknown) {
      return err((e as Error).message);
    }
  }
);

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((err) => {
  console.error("MCP Server error:", err);
  process.exit(1);
});
