import { prisma } from "@/lib/prisma";
import { randomUUID } from "crypto";

const SCHEDULED_EXPORT_TYPE = "mantecato-scheduled-export";

export interface ScheduledExportConfig {
  /** Website to export data for */
  websiteId: string;
  /** What data to export */
  dataSource: "overview" | "pages" | "referrers" | "events" | "sessions" | "devices" | "geo";
  /** Export file format */
  format: "csv" | "json" | "xlsx";
  /** Date range preset to use when running */
  dateRange: string;
  /** Cron-style schedule */
  schedule: "daily" | "weekly" | "monthly";
  /** Day of week for weekly (0=Sun, 1=Mon, ...) */
  weekDay?: number;
  /** Day of month for monthly (1-28) */
  monthDay?: number;
  /** Whether this export is currently active */
  enabled: boolean;
  /** ISO timestamp of last successful run */
  lastRunAt?: string | null;
  /** ISO timestamp of next scheduled run */
  nextRunAt?: string | null;
}

export interface ScheduledExport {
  id: string;
  name: string;
  description: string;
  userId: string;
  websiteId: string;
  config: ScheduledExportConfig;
  createdAt: string;
  updatedAt: string;
}

/**
 * List all scheduled exports for a user.
 */
export async function listScheduledExports(
  userId: string
): Promise<ScheduledExport[]> {
  const reports = await prisma.report.findMany({
    where: {
      type: SCHEDULED_EXPORT_TYPE,
      userId,
    },
    orderBy: { updatedAt: "desc" },
  });

  return reports.map(reportToScheduledExport);
}

/**
 * Get a single scheduled export.
 */
export async function getScheduledExport(
  reportId: string,
  userId: string
): Promise<ScheduledExport | null> {
  const report = await prisma.report.findFirst({
    where: {
      report_id: reportId,
      type: SCHEDULED_EXPORT_TYPE,
      userId,
    },
  });

  return report ? reportToScheduledExport(report) : null;
}

/**
 * Create a new scheduled export.
 */
export async function createScheduledExport(
  userId: string,
  name: string,
  description: string,
  config: ScheduledExportConfig
): Promise<ScheduledExport> {
  // Calculate initial nextRunAt
  config.nextRunAt = computeNextRun(config).toISOString();

  const report = await prisma.report.create({
    data: {
      report_id: randomUUID(),
      userId,
      websiteId: config.websiteId,
      type: SCHEDULED_EXPORT_TYPE,
      name,
      description: description || "",
      parameters: JSON.parse(JSON.stringify(config)),
    },
  });

  return reportToScheduledExport(report);
}

/**
 * Update a scheduled export.
 */
export async function updateScheduledExport(
  reportId: string,
  userId: string,
  updates: {
    name?: string;
    description?: string;
    config?: Partial<ScheduledExportConfig>;
  }
): Promise<ScheduledExport | null> {
  const existing = await prisma.report.findFirst({
    where: { report_id: reportId, type: SCHEDULED_EXPORT_TYPE, userId },
  });
  if (!existing) return null;

  const data: Record<string, unknown> = {};
  if (updates.name !== undefined) data.name = updates.name;
  if (updates.description !== undefined) data.description = updates.description;

  if (updates.config) {
    const existingConfig = existing.parameters as unknown as ScheduledExportConfig;
    const merged = { ...existingConfig, ...updates.config };
    // Recalculate next run if schedule changed
    if (updates.config.schedule || updates.config.enabled !== undefined) {
      merged.nextRunAt = merged.enabled
        ? computeNextRun(merged).toISOString()
        : null;
    }
    data.parameters = JSON.parse(JSON.stringify(merged));
  }

  const report = await prisma.report.update({
    where: { report_id: reportId },
    data,
  });

  return reportToScheduledExport(report);
}

/**
 * Delete a scheduled export.
 */
export async function deleteScheduledExport(
  reportId: string,
  userId: string
): Promise<boolean> {
  const existing = await prisma.report.findFirst({
    where: { report_id: reportId, type: SCHEDULED_EXPORT_TYPE, userId },
  });
  if (!existing) return false;

  await prisma.report.delete({
    where: { report_id: reportId },
  });
  return true;
}

/**
 * Get all due exports (nextRunAt <= now, enabled=true).
 * Used by the cron endpoint.
 */
export async function getDueExports(): Promise<ScheduledExport[]> {
  const reports = await prisma.report.findMany({
    where: {
      type: SCHEDULED_EXPORT_TYPE,
    },
  });

  const now = new Date();
  return reports
    .map(reportToScheduledExport)
    .filter((e) => {
      if (!e.config.enabled) return false;
      if (!e.config.nextRunAt) return false;
      return new Date(e.config.nextRunAt) <= now;
    });
}

/**
 * Mark an export as completed and schedule the next run.
 */
export async function markExportCompleted(
  reportId: string
): Promise<void> {
  const report = await prisma.report.findUnique({
    where: { report_id: reportId },
  });
  if (!report) return;

  const config = report.parameters as unknown as ScheduledExportConfig;
  config.lastRunAt = new Date().toISOString();
  config.nextRunAt = computeNextRun(config).toISOString();

  await prisma.report.update({
    where: { report_id: reportId },
    data: { parameters: JSON.parse(JSON.stringify(config)) },
  });
}

/**
 * Compute the next run date based on the schedule.
 */
function computeNextRun(config: ScheduledExportConfig): Date {
  const now = new Date();

  switch (config.schedule) {
    case "daily": {
      const next = new Date(now);
      next.setDate(next.getDate() + 1);
      next.setHours(6, 0, 0, 0); // Run at 06:00
      return next;
    }
    case "weekly": {
      const next = new Date(now);
      const targetDay = config.weekDay ?? 1; // Default Monday
      const currentDay = next.getDay();
      const daysUntil = (targetDay - currentDay + 7) % 7 || 7;
      next.setDate(next.getDate() + daysUntil);
      next.setHours(6, 0, 0, 0);
      return next;
    }
    case "monthly": {
      const next = new Date(now);
      const targetDay = config.monthDay ?? 1;
      next.setMonth(next.getMonth() + 1);
      next.setDate(Math.min(targetDay, 28));
      next.setHours(6, 0, 0, 0);
      return next;
    }
    default:
      return new Date(now.getTime() + 24 * 60 * 60 * 1000);
  }
}

function reportToScheduledExport(report: {
  report_id: string;
  name: string;
  description: string;
  userId: string;
  websiteId: string;
  parameters: unknown;
  createdAt: Date | null;
  updatedAt: Date | null;
}): ScheduledExport {
  return {
    id: report.report_id,
    name: report.name,
    description: report.description,
    userId: report.userId,
    websiteId: report.websiteId,
    config: report.parameters as ScheduledExportConfig,
    createdAt: report.createdAt?.toISOString() ?? new Date().toISOString(),
    updatedAt: report.updatedAt?.toISOString() ?? new Date().toISOString(),
  };
}
