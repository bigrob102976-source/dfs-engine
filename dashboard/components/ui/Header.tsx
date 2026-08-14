import type { ReactNode } from "react";

/** Top-of-page title + optional description/actions. Every route page
 * should render exactly one of these. */
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-text">{title}</h1>
        {description && <p className="mt-0.5 text-xs text-text-faint">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

/** Titles a group of cards/content within a page (e.g. "Artifact
 * Detail", "Top Pitchers"). Smaller and quieter than PageHeader. */
export function SectionHeader({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="mb-2 flex items-center justify-between">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-text-muted">{title}</h2>
      {action}
    </div>
  );
}
