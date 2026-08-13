import { OptimizerView } from "@/components/OptimizerView";
import { OptimizerWorkspace } from "@/components/optimizer/OptimizerWorkspace";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { listLineupSets } from "@/lib/loaders";
import type { LineupSet } from "@/lib/types";

export const dynamic = "force-dynamic";

/** Milestone 14: the interactive lineup builder is the primary
 * experience here -- pick a slate, browse/lock/exclude/set exposure,
 * configure stacking/objective, click Build, inspect results. Every
 * past run saved today (including ones built through this same
 * workspace, since every Build persists an immutable lineup set exactly
 * like the CLI always has) remains browsable below for reference. */
export default function OptimizerPage() {
  const date = getTodayChicagoDate();
  const loaded = listLineupSets(date);
  const runs = loaded
    .filter((r): r is typeof r & { data: LineupSet } => r.data !== null)
    .map((r) => ({ filename: r.filename, data: r.data }));

  return (
    <div>
      <h1 className="mb-1 text-lg font-semibold text-text">Optimizer</h1>
      <p className="mb-4 text-xs text-text-faint">Select today&apos;s DFS slate, configure constraints, and build lineups.</p>

      <OptimizerWorkspace />

      {runs.length > 0 && (
        <div className="mt-8">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Past Runs Today</h2>
          <OptimizerView runs={runs} />
        </div>
      )}
    </div>
  );
}
