import type { ReactNode } from "react";

/** Consistent bar above a data table: filters/tabs on the left, a
 * result count and any extra controls pinned to the right. */
export function TableToolbar({ children, resultCount }: { children: ReactNode; resultCount?: string }) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      {children}
      {resultCount && <span className="ml-auto shrink-0 text-[11px] text-text-faint">{resultCount}</span>}
    </div>
  );
}
