"use client";

import { useState } from "react";
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
} from "@tanstack/react-table";
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
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: showPagination ? getPaginationRowModel() : undefined,
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
            />
          )}
        </div>
      )}

      {/* Table */}
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
            {table.getRowModel().rows.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="py-8 text-center text-muted-foreground"
                >
                  {emptyMessage}
                </TableCell>
              </TableRow>
            ) : (
              table.getRowModel().rows.map((row) => (
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

      {/* Pagination */}
      {showPagination && table.getPageCount() > 1 && (
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
