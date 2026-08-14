import type { ReactNode } from "react";

/** Beautiful, friendly empty state -- never a bare "nothing here" div,
 * never a terminal command or script path (see MissingDataState for the
 * refresh-capable variant of this same idea). Purely presentational;
 * callers own any action button. */
export function EmptyState({
  icon = "📭",
  title,
  description,
  action,
}: {
  icon?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-[var(--radius-card)] border border-dashed border-border bg-bg-panel px-6 py-12 text-center">
      <div className="mb-3 text-3xl" aria-hidden="true">
        {icon}
      </div>
      <div className="text-sm font-medium text-text">{title}</div>
      {description && <p className="mt-1 max-w-sm text-xs text-text-faint">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
