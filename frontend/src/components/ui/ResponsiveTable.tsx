import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export type ResponsiveTableColumn<Row> = {
  key: string;
  header: string;
  render: (row: Row) => ReactNode;
  mobileHidden?: boolean;
};

type ResponsiveTableProps<Row> = {
  columns: ResponsiveTableColumn<Row>[];
  rows: Row[];
  getRowKey: (row: Row, index: number) => string | number;
  caption?: string;
  emptyState?: ReactNode;
  className?: string;
  tableClassName?: string;
  mobileColumns?: string[];
  mobileAccordion?: boolean;
};

export function ResponsiveTable<Row>({
  columns,
  rows,
  getRowKey,
  caption,
  emptyState,
  className,
  tableClassName,
  mobileColumns,
  mobileAccordion = false,
}: ResponsiveTableProps<Row>) {
  if (rows.length === 0 && emptyState) return <>{emptyState}</>;

  return (
    <div className={cn("w-full", className)}>
      <div className="hidden overflow-x-auto md:block">
        <table className={cn("w-full border-collapse text-left text-sm", tableClassName)}>
          {caption ? <caption className="sr-only">{caption}</caption> : null}
          <thead>
            <tr className="border-b border-border text-text-secondary">
              {columns.map(column => (
                <th key={column.key} scope="col" className="px-[var(--hodi-table-cell-x)] py-[var(--hodi-table-cell-y)] font-medium">
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((row, index) => (
              <tr key={getRowKey(row, index)} className="align-top">
                {columns.map(column => (
                  <td key={column.key} className="px-[var(--hodi-table-cell-x)] py-[var(--hodi-table-cell-y)]">
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="space-y-3 md:hidden">
        {rows.map((row, index) => {
          const visibleColumns = columns.filter(column =>
            !column.mobileHidden && (!mobileColumns || mobileColumns.includes(column.key)),
          );
          const summaryColumn = visibleColumns.find(column => column.key === "period") ?? visibleColumns[0];
          const detailColumns = visibleColumns.filter(column => column.key !== summaryColumn?.key);
          const fields = (items: ResponsiveTableColumn<Row>[]) => items.map(column => (
            <div key={column.key} className="flex min-h-[var(--hodi-control-height)] items-center justify-between gap-4 border-b border-border/70 py-2 last:border-0 last:pb-0">
              <span className="shrink-0 text-xs font-medium text-text-secondary">{column.header}</span>
              <span className="min-w-0 text-right text-sm text-charcoal">{column.render(row)}</span>
            </div>
          ));

          return mobileAccordion ? (
            <details key={getRowKey(row, index)} className="rounded-[var(--hodi-radius-panel)] border border-border bg-surface p-4">
              <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 text-sm font-medium text-charcoal">
                <span>{summaryColumn?.header}</span>
                <span className="text-right">{summaryColumn?.render(row)}</span>
              </summary>
              <div className="mt-2">{fields(detailColumns)}</div>
            </details>
          ) : (
            <article key={getRowKey(row, index)} className="rounded-[var(--hodi-radius-panel)] border border-border bg-surface p-4">
              {fields(visibleColumns)}
            </article>
          );
        })}
      </div>
      {rows.length === 0 && !emptyState ? (
        <p className="px-4 py-8 text-center text-sm text-text-secondary">No records found.</p>
      ) : null}
    </div>
  );
}
