import { RefreshPanel } from "@/components/RefreshPanel";
import { StatusCard } from "@/components/StatusCard";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { buildPipelineStatuses, buildSlateSummary } from "@/lib/pipelineStatus";

export const dynamic = "force-dynamic";

function StatBox({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-border bg-bg-panel p-4">
      <div className="text-[11px] uppercase tracking-wide text-text-faint">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-text">{value}</div>
    </div>
  );
}

/** Today's Slate is always the current America/Chicago date -- never the
 * newest artifact folder found on disk (that's what /dashboard/history
 * and /dashboard/yesterday are for). If nothing has been generated for
 * today yet, the pipeline status cards below honestly show "missing"
 * rather than silently falling back to a previous day. */
export default function TodaysSlatePage() {
  const date = getTodayChicagoDate();
  const summary = buildSlateSummary(date);
  const statuses = buildPipelineStatuses(date);

  return (
    <div>
      <RefreshPanel />

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatBox label="Games" value={summary.gamesOnResearch} />
        <StatBox label="Expected Games (DK slate)" value={summary.gamesOnDkSlate ?? "no DFS slate yet"} />
        <StatBox label="Posted Lineups" value={summary.postedLineupGames} />
        <StatBox label="Missing Lineups" value={summary.missingLineupGames} />
      </div>

      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Artifact Detail</h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {statuses.map((status) => (
          <StatusCard key={status.label} status={status} />
        ))}
      </div>
    </div>
  );
}
