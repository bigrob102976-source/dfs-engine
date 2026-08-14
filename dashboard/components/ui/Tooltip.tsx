import type { ReactNode } from "react";

/** Lightweight, dependency-free hover/focus tooltip. Pure CSS
 * visibility toggle (no JS positioning) -- fine for the short,
 * single-line hints this app needs (column explanations, disabled-
 * button reasons). */
export function Tooltip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="group relative inline-flex">
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-1.5 -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-bg-panel-raised px-2 py-1 text-[11px] text-text opacity-0 shadow-[var(--shadow-popover)] transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100"
      >
        {label}
      </span>
    </span>
  );
}
