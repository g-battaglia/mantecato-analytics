"use client";

import { useState, useRef } from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  getFilteredRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
  type ColumnFiltersState,
  type Row,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ArrowUpDown, ArrowUp, ArrowDown, ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { ExportMenu } from "@/components/export/ExportMenu";
import type { ExportColumn } from "@/lib/export";

/** Threshold above which virtualization is automatically enabled */
const VIRTUALIZATION_THRESHOLD = 200;

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[];
  data: TData[];
  loading?: boolean;
  emptyMessage?: string;
  onRowClick?: (row: TData) => void;
  searchColumn?: string;
  searchPlaceholder?: string;
  pageSize?: number;
  showPagination?: boolean;
  compact?: boolean;
  /** Enable export menu. Pass a filename (without extension) to enable. */
  exportFilename?: string;
  /** Override which columns to export. Defaults to all columns with accessorKey. */
  exportColumns?: ExportColumn[];
  /** Force virtualization on/off. Auto-enabled when data exceeds threshold. */
  virtualize?: boolean;
  /** Max height of the virtual scroll container (default 600px). */
  virtualHeight?: number;
  /** Ref to DOM element for visual export (PDF/PNG) */
  captureRef?: React.RefObject<HTMLElement | null>;
  /** Title for PDF export */
  pdfTitle?: string;
}

export function DataTable<TData, TValue>({
  columns,
  data,
  loading = false,
  emptyMessage = "No data",
  onRowClick,
  searchColumn,
  searchPlaceholder = "Search...",
  pageSize = 10,
  showPagination = true,
  compact = false,
  exportFilename,
  exportColumns,
  virtualize,
  virtualHeight = 600,
  captureRef,
  pdfTitle,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);

  // Auto-detect whether to virtualize
  const shouldVirtualize = virtualize ?? data.length >= VIRTUALIZATION_THRESHOLD;
  // When virtualizing, disable pagination so all rows are available to the virtualizer
  const usePagination = showPagination && !shouldVirtualize;

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: usePagination ? getPaginationRowModel() : undefined,
    getFilteredRowModel: searchColumn ? getFilteredRowModel() : undefined,
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    state: { sorting, columnFilters },
    initialState: { pagination: { pageSize } },
  });

  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: Math.min(pageSize, 8) }).map((_, i) => (
          <Skeleton key={i} className={cn("w-full", compact ? "h-6" : "h-8")} />
        ))}
      </div>
    );
  }

  // Derive export columns from ColumnDefs if not explicitly provided
  const resolvedExportColumns: ExportColumn[] | undefined =
    exportFilename
      ? exportColumns ??
        columns
          .filter((c) => "accessorKey" in c && c.accessorKey)
          .map((c) => {
            const key = String((c as { accessorKey: string }).accessorKey);
            const headerDef = c.header;
            const header =
              typeof headerDef === "string" ? headerDef : key;
            return { key, header };
          })
      : undefined;

  const rows = table.getRowModel().rows;

  return (
    <div className="space-y-3">
      {/* Toolbar: search + export */}
      {(searchColumn || exportFilename) && (
        <div className="flex items-center justify-between gap-2">
          {searchColumn ? (
            <Input
              placeholder={searchPlaceholder}
              value={
                (table.getColumn(searchColumn)?.getFilterValue() as string) ?? ""
              }
              onChange={(e) =>
                table.getColumn(searchColumn)?.setFilterValue(e.target.value)
              }
              className="h-8 max-w-sm text-xs"
            />
          ) : (
            <div />
          )}
          {exportFilename && resolvedExportColumns && (
            <ExportMenu
              data={data as Record<string, unknown>[]}
              columns={resolvedExportColumns}
              filename={exportFilename}
              captureRef={captureRef}
              pdfTitle={pdfTitle}
            />
          )}
        </div>
      )}

      {/* Table — virtualized or standard */}
      {shouldVirtualize ? (
        <VirtualizedTableBody
          rows={rows}
          columns={columns}
          compact={compact}
          emptyMessage={emptyMessage}
          onRowClick={onRowClick}
          maxHeight={virtualHeight}
        />
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              {table.getHeaderGroups().map((headerGroup) => (
                <TableRow key={headerGroup.id}>
                  {headerGroup.headers.map((header) => {
                    const canSort = header.column.getCanSort();
                    const sorted = header.column.getIsSorted();
                    return (
                      <TableHead
                        key={header.id}
                        className={cn(
                          compact && "h-8 px-2 text-xs",
                          canSort && "cursor-pointer select-none"
                        )}
                        onClick={
                          canSort
                            ? header.column.getToggleSortingHandler()
                            : undefined
                        }
                      >
                        <div className="flex items-center gap-1">
                          {header.isPlaceholder
                            ? null
                            : flexRender(
                                header.column.columnDef.header,
                                header.getContext()
                              )}
                          {canSort && (
                            <span className="text-muted-foreground">
                              {sorted === "asc" ? (
                                <ArrowUp className="h-3 w-3" />
                              ) : sorted === "desc" ? (
                                <ArrowDown className="h-3 w-3" />
                              ) : (
                                <ArrowUpDown className="h-3 w-3 opacity-50" />
                              )}
                            </span>
                          )}
                        </div>
                      </TableHead>
                    );
                  })}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {rows.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={columns.length}
                    className="py-8 text-center text-muted-foreground"
                  >
                    {emptyMessage}
                  </TableCell>
                </TableRow>
              ) : (
                rows.map((row) => (
                  <TableRow
                    key={row.id}
                    className={cn(onRowClick && "cursor-pointer")}
                    onClick={() => onRowClick?.(row.original)}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <TableCell
                        key={cell.id}
                        className={cn(compact && "h-8 px-2 py-1 text-xs")}
                      >
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext()
                        )}
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Pagination (only for non-virtualized) */}
      {usePagination && table.getPageCount() > 1 && (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>
              {table.getState().pagination.pageIndex * pageSize + 1}-
              {Math.min(
                (table.getState().pagination.pageIndex + 1) * pageSize,
                table.getFilteredRowModel().rows.length
              )}{" "}
              of {table.getFilteredRowModel().rows.length}
            </span>
            <Select
              value={String(table.getState().pagination.pageSize)}
              onValueChange={(v) => table.setPageSize(Number(v))}
            >
              <SelectTrigger className="h-7 w-[70px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[10, 25, 50, 100].map((size) => (
                  <SelectItem key={size} value={String(size)}>
                    {size}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              className="h-7 w-7 p-0"
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </Button>
            <span className="min-w-[60px] text-center text-xs text-muted-foreground">
              {table.getState().pagination.pageIndex + 1} / {table.getPageCount()}
            </span>
            <Button
              variant="outline"
              size="sm"
              className="h-7 w-7 p-0"
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* Virtual info bar */}
      {shouldVirtualize && rows.length > 0 && (
        <div className="text-xs text-muted-foreground">
          {rows.length.toLocaleString()} rows (scroll to view)
        </div>
      )}
    </div>
  );
}

// --- Virtualized Table Body ---

function VirtualizedTableBody<TData, TValue>({
  rows,
  columns,
  compact,
  emptyMessage,
  onRowClick,
  maxHeight,
}: {
  rows: Row<TData>[];
  columns: ColumnDef<TData, TValue>[];
  compact: boolean;
  emptyMessage: string;
  onRowClick?: (row: TData) => void;
  maxHeight: number;
}) {
  const parentRef = useRef<HTMLDivElement>(null);
  const rowHeight = compact ? 32 : 40;

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 20,
  });

  if (rows.length === 0) {
    return (
      <div className="rounded-md border">
        <Table>
          <TableBody>
            <TableRow>
              <TableCell
                colSpan={columns.length}
                className="py-8 text-center text-muted-foreground"
              >
                {emptyMessage}
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>
    );
  }

  return (
    <div className="rounded-md border">
      {/* Sticky header */}
      <Table>
        <TableHeader>
          <TableRow>
            {rows[0]?.getVisibleCells().map((cell) => {
              const header = cell.column.columnDef.header;
              return (
                <TableHead
                  key={cell.column.id}
                  className={cn(compact && "h-8 px-2 text-xs")}
                >
                  {typeof header === "function"
                    ? flexRender(header, {
                        column: cell.column,
                        header: cell.column.columnDef,
                        table: cell.getContext().table,
                      } as never)
                    : header}
                </TableHead>
              );
            })}
          </TableRow>
        </TableHeader>
      </Table>

      {/* Scrollable virtualized body */}
      <div
        ref={parentRef}
        className="overflow-auto"
        style={{ maxHeight }}
      >
        <div
          style={{
            height: `${virtualizer.getTotalSize()}px`,
            width: "100%",
            position: "relative",
          }}
        >
          <Table>
            <TableBody>
              {virtualizer.getVirtualItems().map((virtualRow) => {
                const row = rows[virtualRow.index];
                return (
                  <TableRow
                    key={row.id}
                    data-index={virtualRow.index}
                    ref={(node) => virtualizer.measureElement(node)}
                    className={cn(onRowClick && "cursor-pointer")}
                    onClick={() => onRowClick?.(row.original)}
                    style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      width: "100%",
                      transform: `translateY(${virtualRow.start}px)`,
                    }}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <TableCell
                        key={cell.id}
                        className={cn(compact && "h-8 px-2 py-1 text-xs")}
                      >
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext()
                        )}
                      </TableCell>
                    ))}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}

/**
 * Helper to create a numeric column with right-alignment and tabular nums.
 */
export function numericColumn<T>(
  accessorKey: string,
  header: string,
  formatter?: (value: number) => string
): ColumnDef<T> {
  return {
    accessorKey,
    header: () => <span className="flex justify-end">{header}</span>,
    cell: ({ getValue }) => {
      const v = getValue() as number;
      return (
        <span className="flex justify-end tabular-nums">
          {formatter ? formatter(v) : v?.toLocaleString() ?? "--"}
        </span>
      );
    },
  };
}

/**
 * Helper to create a percentage column with color coding.
 */
export function percentColumn<T>(
  accessorKey: string,
  header: string
): ColumnDef<T> {
  return {
    accessorKey,
    header: () => <span className="flex justify-end">{header}</span>,
    cell: ({ getValue }) => {
      const v = getValue() as number;
      return (
        <span className="flex justify-end tabular-nums">
          {v != null ? `${v.toFixed(1)}%` : "--"}
        </span>
      );
    },
  };
}
