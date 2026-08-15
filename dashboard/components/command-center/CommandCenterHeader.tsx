import Link from "next/link";

import { CommandCenterRefreshButton } from "./CommandCenterRefreshButton";

function formatTimestamp(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

/** Command Center top header: brand, "Today's Slate", date, a link to
 * the real per-slate picker (Optimizer already owns that interaction --
 * this never duplicates it), a Provider badge, Last Updated, and
 * Refresh. Every value is a prop the Server Component page already
 * computed from already-loaded snapshots -- no client fetch, no
 * subprocess call, no added backend runtime. */
export function CommandCenterHeader({
  date,
  gameCount,
  providerName,
  isMock,
  selectedSlateId,
  lastUpdated,
}: {
  date: string;
  gameCount: number;
  providerName: string | null;
  isMock: boolean;
  selectedSlateId: string | null;
  lastUpdated: string | null;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-4 rounded-[var(--radius-card)] border border-border bg-bg-panel/80 p-5 shadow-[var(--shadow-card)] backdrop-blur">
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-gold">Big Money DFS</div>
        <h1 className="mt-0.5 text-2xl font-semibold tracking-tight text-text">Today&apos;s Slate</h1>
        <p className="mt-0.5 text-xs text-text-faint">
          America/Chicago · {date} · {gameCount} game{gameCount === 1 ? "" : "s"}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <Link
          href="/dashboard/optimizer"
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

        <CommandCenterRefreshButton />
      </div>
    </div>
  );
}
