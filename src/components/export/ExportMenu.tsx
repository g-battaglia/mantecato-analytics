"use client";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Download, FileSpreadsheet, FileJson, FileText } from "lucide-react";
import { exportData, type ExportColumn } from "@/lib/export";

interface ExportMenuProps {
  data: Record<string, unknown>[];
  columns: ExportColumn[];
  filename?: string;
  disabled?: boolean;
}

export function ExportMenu({
  data,
  columns,
  filename = "export",
  disabled = false,
}: ExportMenuProps) {
  if (!data.length) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="h-7 gap-1.5 text-xs"
          disabled={disabled}
        >
          <Download className="h-3.5 w-3.5" />
          Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
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
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
