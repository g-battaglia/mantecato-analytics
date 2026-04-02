import * as XLSX from "xlsx";

export interface ExportColumn {
  key: string;
  header: string;
}

/**
 * Extract plain values from data rows using column definitions.
 * Handles nested accessorKeys like "foo.bar".
 */
function extractRows(
  data: Record<string, unknown>[],
  columns: ExportColumn[]
): unknown[][] {
  return data.map((row) =>
    columns.map((col) => {
      const keys = col.key.split(".");
      let value: unknown = row;
      for (const k of keys) {
        value = (value as Record<string, unknown>)?.[k];
      }
      return value ?? "";
    })
  );
}

/**
 * Export data as CSV and trigger a download.
 */
export function exportCSV(
  data: Record<string, unknown>[],
  columns: ExportColumn[],
  filename = "export"
) {
  const headers = columns.map((c) => c.header);
  const rows = extractRows(data, columns);

  const csvContent = [
    headers.map(escapeCSV).join(","),
    ...rows.map((row) => row.map(escapeCSV).join(",")),
  ].join("\n");

  downloadBlob(csvContent, `${filename}.csv`, "text/csv;charset=utf-8;");
}

function escapeCSV(value: unknown): string {
  const str = String(value ?? "");
  if (str.includes(",") || str.includes('"') || str.includes("\n")) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

/**
 * Export data as JSON and trigger a download.
 */
export function exportJSON(
  data: Record<string, unknown>[],
  columns: ExportColumn[],
  filename = "export"
) {
  const rows = data.map((row) => {
    const obj: Record<string, unknown> = {};
    for (const col of columns) {
      const keys = col.key.split(".");
      let value: unknown = row;
      for (const k of keys) {
        value = (value as Record<string, unknown>)?.[k];
      }
      obj[col.header] = value ?? null;
    }
    return obj;
  });

  const json = JSON.stringify(rows, null, 2);
  downloadBlob(json, `${filename}.json`, "application/json;charset=utf-8;");
}

/**
 * Export data as an Excel (.xlsx) file and trigger a download.
 */
export function exportExcel(
  data: Record<string, unknown>[],
  columns: ExportColumn[],
  filename = "export",
  sheetName = "Data"
) {
  const headers = columns.map((c) => c.header);
  const rows = extractRows(data, columns);

  const ws = XLSX.utils.aoa_to_sheet([headers, ...rows]);

  // Auto-size columns based on content
  const colWidths = headers.map((h, i) => {
    const maxLen = Math.max(
      h.length,
      ...rows.map((r) => String(r[i] ?? "").length)
    );
    return { wch: Math.min(maxLen + 2, 50) };
  });
  ws["!cols"] = colWidths;

  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, sheetName);
  XLSX.writeFile(wb, `${filename}.xlsx`);
}

/**
 * Export data in the specified format.
 */
export function exportData(
  format: "csv" | "json" | "xlsx",
  data: Record<string, unknown>[],
  columns: ExportColumn[],
  filename = "export"
) {
  switch (format) {
    case "csv":
      return exportCSV(data, columns, filename);
    case "json":
      return exportJSON(data, columns, filename);
    case "xlsx":
      return exportExcel(data, columns, filename);
  }
}

function downloadBlob(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
