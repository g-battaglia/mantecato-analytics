import { prisma } from "@/lib/prisma";
import type { Dashboard, DashboardConfig } from "@/lib/dashboard-types";
import { randomUUID } from "crypto";

const DASHBOARD_TYPE = "mantecato-dashboard";

/**
 * List all dashboards for a user (across all sites, or filtered by site).
 */
export async function listDashboards(
  userId: string,
  websiteId?: string
): Promise<Dashboard[]> {
  const where: Record<string, unknown> = {
    type: DASHBOARD_TYPE,
    userId,
  };
  if (websiteId) where.websiteId = websiteId;

  const reports = await prisma.report.findMany({
    where,
    orderBy: { updatedAt: "desc" },
  });

  return reports.map(reportToDashboard);
}

/**
 * Get a single dashboard by ID.
 */
export async function getDashboard(
  reportId: string,
  userId: string
): Promise<Dashboard | null> {
  const report = await prisma.report.findFirst({
    where: {
      report_id: reportId,
      type: DASHBOARD_TYPE,
      userId,
    },
  });

  return report ? reportToDashboard(report) : null;
}

/**
 * Create a new dashboard.
 */
export async function createDashboard(
  userId: string,
  websiteId: string,
  name: string,
  description: string,
  config: DashboardConfig
): Promise<Dashboard> {
  const report = await prisma.report.create({
    data: {
      report_id: randomUUID(),
      userId,
      websiteId,
      type: DASHBOARD_TYPE,
      name,
      description: description || "",
      parameters: JSON.parse(JSON.stringify(config)),
    },
  });

  return reportToDashboard(report);
}

/**
 * Update an existing dashboard.
 */
export async function updateDashboard(
  reportId: string,
  userId: string,
  updates: {
    name?: string;
    description?: string;
    config?: DashboardConfig;
  }
): Promise<Dashboard | null> {
  // Verify ownership
  const existing = await prisma.report.findFirst({
    where: { report_id: reportId, type: DASHBOARD_TYPE, userId },
  });
  if (!existing) return null;

  const data: Record<string, unknown> = {};
  if (updates.name !== undefined) data.name = updates.name;
  if (updates.description !== undefined) data.description = updates.description;
  if (updates.config !== undefined)
    data.parameters = updates.config as unknown as Record<string, unknown>;

  const report = await prisma.report.update({
    where: { report_id: reportId },
    data,
  });

  return reportToDashboard(report);
}

/**
 * Delete a dashboard.
 */
export async function deleteDashboard(
  reportId: string,
  userId: string
): Promise<boolean> {
  const existing = await prisma.report.findFirst({
    where: { report_id: reportId, type: DASHBOARD_TYPE, userId },
  });
  if (!existing) return false;

  await prisma.report.delete({
    where: { report_id: reportId },
  });
  return true;
}

// Convert Prisma Report to Dashboard
function reportToDashboard(report: {
  report_id: string;
  name: string;
  description: string;
  userId: string;
  websiteId: string;
  parameters: unknown;
  createdAt: Date | null;
  updatedAt: Date | null;
}): Dashboard {
  return {
    id: report.report_id,
    name: report.name,
    description: report.description,
    userId: report.userId,
    websiteId: report.websiteId,
    config: report.parameters as DashboardConfig,
    createdAt: report.createdAt?.toISOString() ?? new Date().toISOString(),
    updatedAt: report.updatedAt?.toISOString() ?? new Date().toISOString(),
  };
}
