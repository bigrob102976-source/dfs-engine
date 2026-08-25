import Link from "next/link";

function formatTimestamp(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

/** Command Center top header: brand, "Today's Slate", date, a link to
 * the real per-slate picker (Optimizer already owns that interaction --
 * this never duplicates it), a Provider badge, and Last Updated. Every
 * value is a prop the Server Component page already computed from
 * already-loaded snapshots -- no client fetch, no subprocess call, no
 * added backend runtime. Milestone 29: the Refresh button that used to
 * live here is gone -- refreshing backend slate data is an admin-only
 * action now (see /admin/slates), and `lastUpdated` reflects the
 * PUBLISHED slate version's own timestamp when a slate is selected
 * (app/dashboard/page.tsx), so a member always sees a consistent,
 * trustworthy answer here without needing a manual refresh control. */
export function CommandCenterHeader({
  date,
  gameCount,
  providerName,
  isMock,
  selectedSlateId,
  lastUpdated,
  viewingSlateLabel,
}: {
  date: string;
  gameCount: number;
  providerName: string | null;
  isMock: boolean;
  /** Optimizer correctness hotfix: this is now the GLOBAL slate
   * selector's current choice (lib/slateContext.ts::resolveSlateContext's
   * `selected?.slateId`) -- the exact same slate every other section of
   * this page (pool/ownership/match report/BlueCollar/etc.) is already
   * scoped to. Previously sourced from a DIFFERENT, staler concept
   * (the last raw provider fetch's own `selected_slate_id`, which does
   * not track the global selector at all), and never threaded onto the
   * "Slate" link below -- so clicking through to the Optimizer silently
   * lost whatever slate a member had actually selected here, landing on
   * the Optimizer's own independent (localStorage-persisted) slate
   * instead. Passed through as `?slate=` on the Optimizer link below,
   * mirroring app/dashboard/stacks/page.tsx's identical "Use This
   * Stack" handoff -- OptimizerWorkspace.tsx already reads and honors
   * that exact param. */
  selectedSlateId: string | null;
  lastUpdated: string | null;
  /** Milestone 26: the label of the slate the global selector currently
   * has active (null = Full Day / All Games) -- the same slate as
   * `selectedSlateId`, just formatted for display. */
  viewingSlateLabel?: string | null;
}) {
  const optimizerHref = selectedSlateId ? `/dashboard/optimizer?slate=${encodeURIComponent(selectedSlateId)}` : "/dashboard/optimizer";
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-4 rounded-[var(--radius-card)] border border-border bg-bg-panel/80 p-5 shadow-[var(--shadow-card)] backdrop-blur">
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-gold">Big Money DFS</div>
        <h1 className="mt-0.5 text-2xl font-semibold tracking-tight text-text">Today&apos;s Slate</h1>
        <p className="mt-0.5 text-xs text-text-faint">
          America/Chicago · {date} · {gameCount} game{gameCount === 1 ? "" : "s"}
          {viewingSlateLabel ? <> · Viewing <span className="text-text-muted">{viewingSlateLabel}</span></> : ""}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <Link
          href={optimizerHref}
          className="flex flex-col items-end gap-0.5 rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-3 py-1.5 text-xs text-text-muted transition-colors duration-150 hover:border-accent hover:text-text"
        >
          <span className="text-[10px] uppercase tracking-wide text-text-faint">Slate</span>
          <span>{selectedSlateId ?? "Select in Optimizer →"}</span>
        </Link>

        <div className="flex flex-col items-end gap-0.5">
          <span className="text-[10px] uppercase tracking-wide text-text-faint">Provider</span>
          {providerName ? (
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${isMock ? "bg-yellow/15 text-yellow" : "bg-gold/15 text-gold"}`}>
              {providerName}
            </span>
          ) : (
            <span className="text-xs text-text-faint">Not connected</span>
          )}
        </div>

        <div className="flex flex-col items-end gap-0.5">
          <span className="text-[10px] uppercase tracking-wide text-text-faint">Last Updated</span>
          <span className="text-xs text-text">{formatTimestamp(lastUpdated)}</span>
        </div>
      </div>
    </div>
  );
}
