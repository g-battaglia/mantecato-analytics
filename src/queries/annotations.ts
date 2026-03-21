import { prisma } from "@/lib/prisma";
import { randomUUID } from "crypto";

const ANNOTATION_TYPE = "mantecato-annotation";

export interface Annotation {
  id: string;
  userId: string;
  websiteId: string;
  title: string;
  description: string;
  date: string; // ISO date string
  color: string;
  createdAt: string;
  updatedAt: string;
}

interface AnnotationConfig {
  date: string;
  color: string;
}

/**
 * List annotations for a website within a date range.
 */
export async function listAnnotations(
  userId: string,
  websiteId: string,
  startDate?: Date,
  endDate?: Date
): Promise<Annotation[]> {
  const reports = await prisma.report.findMany({
    where: {
      type: ANNOTATION_TYPE,
      userId,
      websiteId,
    },
    orderBy: { createdAt: "desc" },
  });

  const annotations = reports.map(reportToAnnotation);

  // Filter by date range if provided
  if (startDate && endDate) {
    const start = startDate.toISOString();
    const end = endDate.toISOString();
    return annotations.filter((a) => a.date >= start && a.date <= end);
  }

  return annotations;
}

/**
 * Create a new annotation.
 */
export async function createAnnotation(
  userId: string,
  websiteId: string,
  title: string,
  description: string,
  date: string,
  color: string = "blue"
): Promise<Annotation> {
  const config: AnnotationConfig = { date, color };

  const report = await prisma.report.create({
    data: {
      report_id: randomUUID(),
      userId,
      websiteId,
      type: ANNOTATION_TYPE,
      name: title,
      description: description || "",
      parameters: JSON.parse(JSON.stringify(config)),
    },
  });

  return reportToAnnotation(report);
}

/**
 * Delete an annotation.
 */
export async function deleteAnnotation(
  reportId: string,
  userId: string
): Promise<boolean> {
  const existing = await prisma.report.findFirst({
    where: { report_id: reportId, type: ANNOTATION_TYPE, userId },
  });
  if (!existing) return false;

  await prisma.report.delete({
    where: { report_id: reportId },
  });
  return true;
}

function reportToAnnotation(report: {
  report_id: string;
  name: string;
  description: string;
  userId: string;
  websiteId: string;
  parameters: unknown;
  createdAt: Date | null;
  updatedAt: Date | null;
}): Annotation {
  const config = report.parameters as AnnotationConfig;
  return {
    id: report.report_id,
    userId: report.userId,
    websiteId: report.websiteId,
    title: report.name,
    description: report.description,
    date: config?.date ?? report.createdAt?.toISOString() ?? new Date().toISOString(),
    color: config?.color ?? "blue",
    createdAt: report.createdAt?.toISOString() ?? new Date().toISOString(),
    updatedAt: report.updatedAt?.toISOString() ?? new Date().toISOString(),
  };
}
