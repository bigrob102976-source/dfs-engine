import { OptimizerView } from "@/components/OptimizerView";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { listLineupSets } from "@/lib/loaders";
import type { LineupSet } from "@/lib/types";

export const dynamic = "force-dynamic";

export default function OptimizerPage() {
  const date = getTodayChicagoDate();
  const loaded = listLineupSets(date);
  const runs = loaded
    .filter((r): r is typeof r & { data: LineupSet } => r.data !== null)
    .map((r) => ({ filename: r.filename, data: r.data }));

  return (
    <div>
      <h1 className="mb-1 text-lg font-semibold text-text">Optimizer</h1>
      <p className="mb-4 text-xs text-text-faint">
        {runs.length > 0
          ? `${runs.length} optimizer run(s) found for ${date}. Click a lineup row to expand its roster.`
          : "No lineups generated yet."}
      </p>
      {runs.length === 0 ? (
        <div className="rounded border border-border bg-bg-panel p-6 text-sm text-text-faint">
          Run: <code className="text-text-muted">python scripts/optimize_dk_lineups.py --date {date ?? "YYYY-MM-DD"} --pool &lt;dk_player_pool_path&gt;</code>
        </div>
      ) : (
        <OptimizerView runs={runs} />
      )}
    </div>
  );
}
