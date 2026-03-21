import { prisma } from "@/lib/prisma";
import { randomUUID } from "crypto";

const SAVED_VIEW_TYPE = "mantecato-saved-view";

export interface SavedViewConfig {
  preset: string;
  customStart?: string | null;
  customEnd?: string | null;
  granularity: string;
  filters: Array<{
    column: string;
    operator: string;
    value: string;
  }>;
  /** The page path this view applies to (e.g. "overview", "pages", "events") */
  page?: string;
}

export interface SavedView {
  id: string;
  name: string;
  description: string;
  userId: string;
  websiteId: string;
  config: SavedViewConfig;
  createdAt: string;
  updatedAt: string;
}

/**
 * List all saved views for a user+site.
 */
export async function listSavedViews(
  userId: string,
  websiteId: string
): Promise<SavedView[]> {
  const reports = await prisma.report.findMany({
    where: {
      type: SAVED_VIEW_TYPE,
      userId,
      websiteId,
    },
    orderBy: { updatedAt: "desc" },
  });

  return reports.map(reportToSavedView);
}

/**
 * Get a single saved view.
 */
export async function getSavedView(
  reportId: string,
  userId: string
): Promise<SavedView | null> {
  const report = await prisma.report.findFirst({
    where: {
      report_id: reportId,
      type: SAVED_VIEW_TYPE,
      userId,
    },
  });

  return report ? reportToSavedView(report) : null;
}

/**
 * Create a new saved view.
 */
export async function createSavedView(
  userId: string,
  websiteId: string,
  name: string,
  description: string,
  config: SavedViewConfig
): Promise<SavedView> {
  const report = await prisma.report.create({
    data: {
      report_id: randomUUID(),
      userId,
      websiteId,
      type: SAVED_VIEW_TYPE,
      name,
      description: description || "",
      parameters: JSON.parse(JSON.stringify(config)),
    },
  });

  return reportToSavedView(report);
}

/**
 * Update a saved view.
 */
export async function updateSavedView(
  reportId: string,
  userId: string,
  updates: {
    name?: string;
    description?: string;
    config?: SavedViewConfig;
  }
): Promise<SavedView | null> {
  const existing = await prisma.report.findFirst({
    where: { report_id: reportId, type: SAVED_VIEW_TYPE, userId },
  });
  if (!existing) return null;

  const data: Record<string, unknown> = {};
  if (updates.name !== undefined) data.name = updates.name;
  if (updates.description !== undefined) data.description = updates.description;
  if (updates.config !== undefined)
    data.parameters = JSON.parse(JSON.stringify(updates.config));

  const report = await prisma.report.update({
    where: { report_id: reportId },
    data,
  });

  return reportToSavedView(report);
}

/**
 * Delete a saved view.
 */
export async function deleteSavedView(
  reportId: string,
  userId: string
): Promise<boolean> {
  const existing = await prisma.report.findFirst({
    where: { report_id: reportId, type: SAVED_VIEW_TYPE, userId },
  });
  if (!existing) return false;

  await prisma.report.delete({
    where: { report_id: reportId },
  });
  return true;
}

function reportToSavedView(report: {
  report_id: string;
  name: string;
  description: string;
  userId: string;
  websiteId: string;
  parameters: unknown;
  createdAt: Date | null;
  updatedAt: Date | null;
}): SavedView {
  return {
    id: report.report_id,
    name: report.name,
    description: report.description,
    userId: report.userId,
    websiteId: report.websiteId,
    config: report.parameters as SavedViewConfig,
    createdAt: report.createdAt?.toISOString() ?? new Date().toISOString(),
    updatedAt: report.updatedAt?.toISOString() ?? new Date().toISOString(),
  };
}
