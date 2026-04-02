
import { useRef, useCallback, useState } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import {
  Download,
  FileSpreadsheet,
  FileJson,
  FileText,
  Image,
  FileDown,
  Loader2,
} from "lucide-react";
import { exportData, type ExportColumn } from "@/lib/export";

interface ExportMenuProps {
  data: Record<string, unknown>[];
  columns: ExportColumn[];
  filename?: string;
  disabled?: boolean;
  /** Ref to DOM element for visual export (PDF/PNG). If not provided, visual exports are hidden. */
  captureRef?: React.RefObject<HTMLElement | null>;
  /** Title for the PDF export header */
  pdfTitle?: string;
}

export function ExportMenu({
  data,
  columns,
  filename = "export",
  disabled = false,
  captureRef,
  pdfTitle,
}: ExportMenuProps) {
  const [exporting, setExporting] = useState<"png" | "pdf" | null>(null);

  const handleVisualExport = useCallback(
    async (format: "png" | "pdf") => {
      if (!captureRef?.current) return;
      setExporting(format);
      try {
        const { exportPNG, exportPDF } = await import("@/lib/export-visual");
        if (format === "png") {
          await exportPNG(captureRef.current, filename);
        } else {
          await exportPDF(captureRef.current, filename, pdfTitle);
        }
      } catch (err) {
        console.error(`Failed to export ${format}:`, err);
      } finally {
        setExporting(null);
      }
    },
    [captureRef, filename, pdfTitle]
  );

  if (!data.length && !captureRef) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="h-7 gap-1.5 text-xs"
          disabled={disabled || exporting !== null}
        >
          {exporting ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Download className="h-3.5 w-3.5" />
          )}
          {exporting ? `Exporting ${exporting.toUpperCase()}...` : "Export"}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {data.length > 0 && (
          <>
            <DropdownMenuItem
              onClick={() => exportData("csv", data, columns, filename)}
            >
              <FileText className="mr-2 h-3.5 w-3.5" />
              CSV
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => exportData("json", data, columns, filename)}
            >
              <FileJson className="mr-2 h-3.5 w-3.5" />
              JSON
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => exportData("xlsx", data, columns, filename)}
            >
              <FileSpreadsheet className="mr-2 h-3.5 w-3.5" />
              Excel (.xlsx)
            </DropdownMenuItem>
          </>
        )}
        {captureRef && (
          <>
            {data.length > 0 && <DropdownMenuSeparator />}
            <DropdownMenuItem
              onClick={() => handleVisualExport("png")}
              disabled={exporting !== null}
            >
              <Image className="mr-2 h-3.5 w-3.5" />
              PNG Screenshot
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => handleVisualExport("pdf")}
              disabled={exporting !== null}
            >
              <FileDown className="mr-2 h-3.5 w-3.5" />
              PDF Report
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
