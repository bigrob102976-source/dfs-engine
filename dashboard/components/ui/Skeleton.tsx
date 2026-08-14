/** A single pulsing placeholder block. Compose into row/card/table
 * skeletons -- never show a blank page while data loads. */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-bg-panel-raised ${className}`} aria-hidden="true" />;
}

/** Skeleton for a card-shaped region (metric tiles, data cards). */
export function SkeletonCard() {
  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-4">
      <Skeleton className="mb-2 h-3 w-20" />
      <Skeleton className="h-6 w-16" />
    </div>
  );
}

/** Skeleton for a data table -- a header bar plus N shimmering rows. */
export function SkeletonTable({ rows = 6 }: { rows?: number }) {
  return (
    <div className="overflow-hidden rounded-[var(--radius-card)] border border-border">
      <Skeleton className="h-8 w-full rounded-none" />
      <div className="divide-y divide-border-subtle bg-bg-panel">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 px-3 py-2.5">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-3 w-12" />
            <Skeleton className="h-3 w-12" />
            <Skeleton className="ml-auto h-3 w-16" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Full-panel overlay shown while a background action (build, refresh)
 * is running -- keeps the underlying content visible but non-interactive
 * rather than swapping to a blank page. */
export function LoadingOverlay({ label = "Loading..." }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 rounded-[var(--radius-card)] bg-bg/70 backdrop-blur-[1px]"
    >
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-border border-t-accent" aria-hidden="true" />
      <span className="text-xs text-text-muted">{label}</span>
    </div>
  );
}
