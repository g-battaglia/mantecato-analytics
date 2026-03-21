#!/usr/bin/env node
/**
 * Mantecato CLI — analytics from the command line.
 *
 * Usage:
 *   npx mantecato sites
 *   npx mantecato stats --site astrologerstudio.com --period 30d
 *   npx mantecato pages --site astrologerstudio.com --limit 20 --format json
 *   npx mantecato realtime --site astrologerstudio.com
 *
 * All commands support:
 *   --format json|table|csv  (default: table)
 *   --site <name|domain|id>  (required for most commands)
 *   --period <preset>        (default: 30d)
 *   --start <ISO date>       (custom start)
 *   --end <ISO date>         (custom end)
 *   --filter <col:op:val>    (repeatable)
 *   --granularity <auto|minute|hour|day|week|month>
 */
import "dotenv/config";
import { Command, Option } from "commander";
import {
  listSites,
  resolveSiteId,
  parseDateArgs,
  resolveGranularityArg,
  parseFilterArgs,
  formatOutput,
  computeDerivedStats,
  type OutputFormat,
} from "./helpers.js";

import { getWebsiteStats, getPageviewTimeSeries, getTopPages, getTopReferrers, getTopEvents } from "@/queries/stats";
import { getPageMetrics, getPageReferrers, getNextPages } from "@/queries/pageviews";
import { getReferrerMetrics, getUTMDetailMetrics, getChannelMetrics, getClickIdMetrics, getHostnameMetrics } from "@/queries/sources";
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
// Common options
// ---------------------------------------------------------------------------

function addCommonOptions(cmd: Command): Command {
  return cmd
    .option("-s, --site <site>", "Site name, domain, or UUID")
    .option("-p, --period <preset>", "Date range preset (e.g. 7d, 30d, 90d, this_month)", "30d")
    .option("--start <date>", "Custom start date (ISO 8601)")
    .option("--end <date>", "Custom end date (ISO 8601)")
    .option("-f, --format <format>", "Output format: json, table, csv", "table")
    .option("--filter <filter...>", "Filters in column:operator:value format (repeatable)")
    .option("-l, --limit <n>", "Max rows to return", "20")
    .option("-g, --granularity <g>", "Time granularity: auto, minute, hour, day, week, month", "auto");
}

interface CommonOpts {
  site?: string;
  period: string;
  start?: string;
  end?: string;
  format: OutputFormat;
  filter?: string[];
  limit: string;
  granularity: string;
}

async function requireSite(opts: CommonOpts): Promise<string> {
  if (!opts.site) {
    console.error("Error: --site is required. Use `mantecato sites` to list available sites.");
    process.exit(1);
  }
  return resolveSiteId(opts.site);
}

function out(data: unknown, format: OutputFormat, title?: string) {
  console.log(formatOutput(data, format, { title }));
}

// ---------------------------------------------------------------------------
// Program
// ---------------------------------------------------------------------------

const program = new Command();
program
  .name("mantecato")
  .description("Mantecato Analytics CLI — query your Umami analytics data from the terminal")
  .version("0.1.0");

// --- sites ---
program
  .command("sites")
  .description("List all tracked websites")
  .option("-f, --format <format>", "Output format", "table")
  .action(async (opts: { format: OutputFormat }) => {
    const sites = await listSites();
    out(sites, opts.format, "Tracked Sites");
  });

// --- stats ---
addCommonOptions(
  program
    .command("stats")
    .description("Overview stats: pageviews, visitors, visits, bounce rate, avg duration")
).action(async (opts: CommonOpts) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const filters = parseFilterArgs(opts.filter || []);
  const raw = await getWebsiteStats(siteId, range.startDate, range.endDate, filters);
  const derived = computeDerivedStats(raw);
  out(derived, opts.format, "Overview Stats");
});

// --- timeseries ---
addCommonOptions(
  program
    .command("timeseries")
    .description("Pageview & visitor time series")
).action(async (opts: CommonOpts) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const filters = parseFilterArgs(opts.filter || []);
  const gran = resolveGranularityArg(opts.granularity, range);
  const data = await getPageviewTimeSeries(siteId, range.startDate, range.endDate, gran, filters);
  out(data, opts.format, "Traffic Time Series");
});

// --- pages ---
addCommonOptions(
  program
    .command("pages")
    .description("Page analytics: views, visitors, time-on-page, bounce rate")
    .option("--mode <mode>", "Grouping mode: path or slug", "path")
).action(async (opts: CommonOpts & { mode: string }) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const filters = parseFilterArgs(opts.filter || []);
  const data = await getPageMetrics(siteId, range.startDate, range.endDate, +opts.limit, 0, filters, opts.mode as "path" | "slug");
  out(data, opts.format, "Page Analytics");
});

// --- page-detail ---
addCommonOptions(
  program
    .command("page-detail")
    .description("Detailed stats for a specific page: referrers, next pages, time distribution")
    .requiredOption("--url <path>", "URL path to analyze (e.g. /pricing)")
).action(async (opts: CommonOpts & { url: string }) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const [referrers, nextPages] = await Promise.all([
    getPageReferrers(siteId, opts.url, range.startDate, range.endDate, +opts.limit),
    getNextPages(siteId, opts.url, range.startDate, range.endDate, +opts.limit),
  ]);
  if (opts.format === "json") {
    out({ referrers, nextPages }, opts.format);
  } else {
    out(referrers, opts.format, `Referrers for ${opts.url}`);
    out(nextPages, opts.format, `Next Pages from ${opts.url}`);
  }
});

// --- sources ---
addCommonOptions(
  program
    .command("sources")
    .description("Traffic sources: referrers with bounce rate and duration")
).action(async (opts: CommonOpts) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const filters = parseFilterArgs(opts.filter || []);
  const data = await getReferrerMetrics(siteId, range.startDate, range.endDate, +opts.limit, filters);
  out(data, opts.format, "Traffic Sources");
});

// --- channels ---
addCommonOptions(
  program
    .command("channels")
    .description("Auto-grouped traffic channels (Organic Search, Direct, Social, etc.)")
).action(async (opts: CommonOpts) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const filters = parseFilterArgs(opts.filter || []);
  const data = await getChannelMetrics(siteId, range.startDate, range.endDate, filters);
  out(data, opts.format, "Traffic Channels");
});

// --- utm ---
addCommonOptions(
  program
    .command("utm")
    .description("UTM parameter breakdown")
    .option("--dimension <dim>", "UTM dimension: utm_source, utm_medium, utm_campaign, utm_content, utm_term", "utm_source")
).action(async (opts: CommonOpts & { dimension: string }) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const filters = parseFilterArgs(opts.filter || []);
  const data = await getUTMDetailMetrics(siteId, range.startDate, range.endDate, opts.dimension as "utm_source", +opts.limit, filters);
  out(data, opts.format, `UTM: ${opts.dimension}`);
});

// --- clickids ---
addCommonOptions(
  program
    .command("clickids")
    .description("Click ID analysis (gclid, fbclid, etc.)")
).action(async (opts: CommonOpts) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const filters = parseFilterArgs(opts.filter || []);
  const data = await getClickIdMetrics(siteId, range.startDate, range.endDate, filters);
  out(data, opts.format, "Click IDs");
});

// --- hostnames ---
addCommonOptions(
  program
    .command("hostnames")
    .description("Hostname breakdown (for multi-subdomain tracking)")
).action(async (opts: CommonOpts) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const filters = parseFilterArgs(opts.filter || []);
  const data = await getHostnameMetrics(siteId, range.startDate, range.endDate, +opts.limit, filters);
  out(data, opts.format, "Hostnames");
});

// --- events ---
addCommonOptions(
  program
    .command("events")
    .description("Custom event metrics")
).action(async (opts: CommonOpts) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const filters = parseFilterArgs(opts.filter || []);
  const data = await getEventMetrics(siteId, range.startDate, range.endDate, +opts.limit, filters);
  out(data, opts.format, "Custom Events");
});

// --- event-detail ---
addCommonOptions(
  program
    .command("event-detail")
    .description("Time series and properties for a specific event")
    .requiredOption("--event <name>", "Event name to analyze")
).action(async (opts: CommonOpts & { event: string }) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const gran = resolveGranularityArg(opts.granularity, range);
  const filters = parseFilterArgs(opts.filter || []);
  const [timeseries, properties] = await Promise.all([
    getEventTimeSeries(siteId, opts.event, range.startDate, range.endDate, gran, filters),
    getEventProperties(siteId, opts.event, range.startDate, range.endDate, +opts.limit),
  ]);
  if (opts.format === "json") {
    out({ timeseries, properties }, opts.format);
  } else {
    out(timeseries, opts.format, `Event "${opts.event}" Time Series`);
    out(properties, opts.format, `Event "${opts.event}" Properties`);
  }
});

// --- sessions ---
addCommonOptions(
  program
    .command("sessions")
    .description("Session list with location, device, and engagement data")
    .option("--visited-page <path>", "Filter to sessions that visited a specific page")
    .option("--triggered-event <event>", "Filter to sessions that triggered a specific event")
).action(async (opts: CommonOpts & { visitedPage?: string; triggeredEvent?: string }) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const filters = parseFilterArgs(opts.filter || []);
  const data = await getSessionList(siteId, range.startDate, range.endDate, +opts.limit, 0, filters, opts.visitedPage, opts.triggeredEvent);
  out(data, opts.format, "Sessions");
});

// --- session-activity ---
program
  .command("session-activity")
  .description("Full event replay for a specific session")
  .requiredOption("--session-id <id>", "Session UUID")
  .requiredOption("-s, --site <site>", "Site name, domain, or UUID")
  .option("-f, --format <format>", "Output format", "table")
  .action(async (opts: { sessionId: string; site: string; format: OutputFormat }) => {
    const siteId = await resolveSiteId(opts.site);
    const data = await getSessionActivity(opts.sessionId, siteId);
    out(data, opts.format, "Session Activity");
  });

// --- devices ---
addCommonOptions(
  program
    .command("devices")
    .description("Device, browser, OS, screen, and language breakdown")
    .option("--dimension <dim>", "Dimension: browser, os, device, screen, language", "device")
).action(async (opts: CommonOpts & { dimension: string }) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const filters = parseFilterArgs(opts.filter || []);
  const data = await getDeviceMetrics(siteId, range.startDate, range.endDate, opts.dimension as "browser", +opts.limit, filters);
  out(data, opts.format, `Devices: ${opts.dimension}`);
});

// --- geo ---
addCommonOptions(
  program
    .command("geo")
    .description("Geographic breakdown of visitors")
    .option("--level <level>", "Drill-down level: country, region, city", "country")
    .option("--country <code>", "Filter by country code (for region/city drill-down)")
    .option("--region <name>", "Filter by region (for city drill-down)")
).action(async (opts: CommonOpts & { level: string; country?: string; region?: string }) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const filters = parseFilterArgs(opts.filter || []);
  const data = await getGeoMetrics(siteId, range.startDate, range.endDate, opts.level as "country", opts.country, opts.region, +opts.limit, filters);
  out(data, opts.format, `Geo: ${opts.level}`);
});

// --- realtime ---
program
  .command("realtime")
  .description("Real-time active visitors and recent events")
  .requiredOption("-s, --site <site>", "Site name, domain, or UUID")
  .option("-f, --format <format>", "Output format", "table")
  .action(async (opts: { site: string; format: OutputFormat }) => {
    const siteId = await resolveSiteId(opts.site);
    const [active, pages, events] = await Promise.all([
      getActiveVisitors(siteId),
      getCurrentPages(siteId),
      getRecentEvents(siteId),
    ]);
    if (opts.format === "json") {
      out({ active, pages, events }, opts.format);
    } else {
      out({ activeVisitors: active.count }, opts.format, "Realtime");
      if (active.visitors.length > 0) out(active.visitors, opts.format, "Active Visitors");
      if (pages.length > 0) out(pages, opts.format, "Current Pages");
      if (events.length > 0) out(events, opts.format, "Recent Events");
    }
  });

// --- compare ---
addCommonOptions(
  program
    .command("compare")
    .description("Compare current period vs previous period")
    .option("--compare-mode <mode>", "Comparison mode: previous_period, previous_year", "previous_period")
).action(async (opts: CommonOpts & { compareMode: string }) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const prevRange = getComparisonRange(range, opts.compareMode as "previous_period" | "previous_year");
  const data = await getComparisonStats(siteId, range.startDate, range.endDate, prevRange.startDate, prevRange.endDate);
  const current = data.find((d) => d.period === "current");
  const previous = data.find((d) => d.period === "previous");
  if (opts.format === "json") {
    out({ current: current ? computeDerivedStats(current) : null, previous: previous ? computeDerivedStats(previous) : null }, opts.format);
  } else {
    if (current) out(computeDerivedStats(current), opts.format, "Current Period");
    if (previous) out(computeDerivedStats(previous), opts.format, "Previous Period");
  }
});

// --- retention ---
addCommonOptions(
  program
    .command("retention")
    .description("Cohort retention analysis")
    .addOption(new Option("--retention-granularity <g>", "Cohort granularity").choices(["week", "month"]).default("week"))
).action(async (opts: CommonOpts & { retentionGranularity: string }) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const data = await getRetention(siteId, range.startDate, range.endDate, opts.retentionGranularity as "week" | "month");
  if (opts.format === "json") {
    out(data, opts.format);
  } else {
    // Flatten retention for table view
    const rows = data.map((c) => ({
      cohort: c.cohort,
      users: c.cohortSize,
      ...Object.fromEntries(c.periods.slice(0, 8).map((p, i) => [`P${i}`, p > 0 ? `${p}%` : "-"])),
    }));
    out(rows, opts.format, "Cohort Retention");
  }
});

// --- funnel ---
addCommonOptions(
  program
    .command("funnel")
    .description("Funnel analysis — define steps and see conversion rates")
    .requiredOption("--steps <steps>", "Steps as JSON array: [{\"type\":\"url\",\"value\":\"/\"},...] or comma-separated URLs")
    .option("--window <minutes>", "Conversion window in minutes", "60")
).action(async (opts: CommonOpts & { steps: string; window: string }) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  let steps: Array<{ type: "url" | "event"; value: string }>;
  try {
    steps = JSON.parse(opts.steps);
  } catch {
    // Simple comma-separated URLs
    steps = opts.steps.split(",").map((s) => ({ type: "url" as const, value: s.trim() }));
  }
  if (steps.length < 2) {
    console.error("Error: at least 2 funnel steps are required.");
    process.exit(1);
  }
  const data = await getFunnel(siteId, range.startDate, range.endDate, steps, +opts.window);
  out(data, opts.format, "Funnel");
});

// --- journeys ---
addCommonOptions(
  program
    .command("journeys")
    .description("User journey paths (page sequences)")
    .option("--path-length <n>", "Number of steps in path", "3")
).action(async (opts: CommonOpts & { pathLength: string }) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const data = await getJourneys(siteId, range.startDate, range.endDate, +opts.pathLength, +opts.limit);
  out(data, opts.format, "User Journeys");
});

// --- revenue ---
addCommonOptions(
  program
    .command("revenue")
    .description("Revenue analytics: summary, time series, by event, by country")
    .option("--view <view>", "View: summary, timeseries, by-event, by-country", "summary")
).action(async (opts: CommonOpts & { view: string }) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const gran = resolveGranularityArg(opts.granularity, range);
  switch (opts.view) {
    case "summary": {
      const data = await getRevenueSummary(siteId, range.startDate, range.endDate);
      out(data, opts.format, "Revenue Summary");
      break;
    }
    case "timeseries": {
      const data = await getRevenueTimeSeries(siteId, range.startDate, range.endDate, gran);
      out(data, opts.format, "Revenue Time Series");
      break;
    }
    case "by-event": {
      const data = await getRevenueByEvent(siteId, range.startDate, range.endDate, +opts.limit);
      out(data, opts.format, "Revenue by Event");
      break;
    }
    case "by-country": {
      const data = await getRevenueByCountry(siteId, range.startDate, range.endDate, +opts.limit);
      out(data, opts.format, "Revenue by Country");
      break;
    }
    default:
      console.error(`Unknown view: ${opts.view}. Use: summary, timeseries, by-event, by-country`);
      process.exit(1);
  }
});

// --- engagement ---
addCommonOptions(
  program
    .command("engagement")
    .description("Engagement analytics: duration distribution, percentiles, bounce rates")
    .option("--view <view>", "View: distribution, percentiles, by-page, bounce-by-page, bounce-by-source", "percentiles")
).action(async (opts: CommonOpts & { view: string }) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const filters = parseFilterArgs(opts.filter || []);
  switch (opts.view) {
    case "distribution": {
      const data = await getDurationDistribution(siteId, range.startDate, range.endDate, filters);
      out(data, opts.format, "Duration Distribution");
      break;
    }
    case "percentiles": {
      const data = await getDurationPercentiles(siteId, range.startDate, range.endDate, filters);
      out(data, opts.format, "Duration Percentiles");
      break;
    }
    case "by-page": {
      const data = await getDurationByPage(siteId, range.startDate, range.endDate, +opts.limit, filters);
      out(data, opts.format, "Time on Page");
      break;
    }
    case "bounce-by-page": {
      const data = await getBounceRateByPage(siteId, range.startDate, range.endDate, +opts.limit, filters);
      out(data, opts.format, "Bounce Rate by Entry Page");
      break;
    }
    case "bounce-by-source": {
      const data = await getBounceRateBySource(siteId, range.startDate, range.endDate, +opts.limit, filters);
      out(data, opts.format, "Bounce Rate by Source");
      break;
    }
    default:
      console.error(`Unknown view: ${opts.view}. Use: distribution, percentiles, by-page, bounce-by-page, bounce-by-source`);
      process.exit(1);
  }
});

// --- filter-values ---
program
  .command("filter-values")
  .description("Get available values for a filter column (for autocomplete)")
  .requiredOption("-s, --site <site>", "Site name, domain, or UUID")
  .requiredOption("--column <col>", "Column: browser, os, device, country, url_path, event_name, etc.")
  .option("-p, --period <preset>", "Date range preset", "30d")
  .option("--start <date>", "Custom start date")
  .option("--end <date>", "Custom end date")
  .option("--search <q>", "Search filter for values")
  .option("-l, --limit <n>", "Max values", "50")
  .option("-f, --format <format>", "Output format", "table")
  .action(async (opts: { site: string; column: string; period: string; start?: string; end?: string; search?: string; limit: string; format: OutputFormat }) => {
    const siteId = await resolveSiteId(opts.site);
    const range = parseDateArgs(opts.period, opts.start, opts.end);
    const values = await getFilterValues(siteId, opts.column, range.startDate, range.endDate, opts.search, +opts.limit);
    if (opts.format === "json") {
      out(values, opts.format);
    } else {
      out(values.map((v) => ({ value: v })), opts.format, `Filter Values: ${opts.column}`);
    }
  });

// --- top-pages (quick alias) ---
addCommonOptions(
  program
    .command("top-pages")
    .description("Quick top pages by visitors")
).action(async (opts: CommonOpts) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const filters = parseFilterArgs(opts.filter || []);
  const data = await getTopPages(siteId, range.startDate, range.endDate, +opts.limit, filters);
  out(data, opts.format, "Top Pages");
});

// --- top-referrers (quick alias) ---
addCommonOptions(
  program
    .command("top-referrers")
    .description("Quick top referrers by visitors")
).action(async (opts: CommonOpts) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const filters = parseFilterArgs(opts.filter || []);
  const data = await getTopReferrers(siteId, range.startDate, range.endDate, +opts.limit, filters);
  out(data, opts.format, "Top Referrers");
});

// --- top-events (quick alias) ---
addCommonOptions(
  program
    .command("top-events")
    .description("Quick top custom events")
).action(async (opts: CommonOpts) => {
  const siteId = await requireSite(opts);
  const range = parseDateArgs(opts.period, opts.start, opts.end);
  const filters = parseFilterArgs(opts.filter || []);
  const data = await getTopEvents(siteId, range.startDate, range.endDate, +opts.limit, filters);
  out(data, opts.format, "Top Events");
});

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------

program.parseAsync(process.argv).catch((err) => {
  console.error("Error:", err.message || err);
  process.exit(1);
});
