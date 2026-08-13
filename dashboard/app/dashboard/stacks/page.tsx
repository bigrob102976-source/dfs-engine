import { getTodayChicagoDate } from "@/lib/currentDate";
import { loadLatestOwnershipSnapshot, loadLatestBatterSnapshot } from "@/lib/loaders";
import { buildHitterRows } from "@/lib/normalize";
import { buildStackSummaries } from "@/lib/stacks";

export const dynamic = "force-dynamic";

function fmt(v: number | null): string {
  return v === null ? "--" : v.toFixed(1);
}

export default function StacksPage() {
  const date = getTodayChicagoDate();
  const batterSnapshot = date ? loadLatestBatterSnapshot(date).data : null;
  const ownership = date ? loadLatestOwnershipSnapshot(date).data : null;

  const rows = buildHitterRows(batterSnapshot?.hitters ?? [], ownership, null);
  const stacks = buildStackSummaries(rows, ownership?.team_popularity ?? {});

  return (
    <div>
      <h1 className="mb-1 text-lg font-semibold text-text">Stacks</h1>
      <p className="mb-4 text-xs text-text-faint">
        Existing per-team data summarized -- no simulation. Team Popularity requires an ownership snapshot to be loaded.
      </p>

      {!batterSnapshot ? (
        <div className="rounded border border-border bg-bg-panel p-6 text-sm text-text-faint">Batter snapshot not generated yet.</div>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {stacks.map((s) => (
            <div key={s.team} className="rounded-lg border border-border bg-bg-panel p-4">
              <div className="mb-3 flex items-center justify-between">
                <span className="text-sm font-semibold text-text">{s.team}</span>
                <span className="text-[11px] text-text-faint">{s.confirmedHitterCount} confirmed hitters</span>
              </div>
              <div className="mb-3 grid grid-cols-3 gap-2 text-center">
                <div>
                  <div className="text-[10px] text-text-faint">Avg Proj</div>
                  <div className="text-sm text-text">{fmt(s.averageProjection)}</div>
                </div>
                <div>
                  <div className="text-[10px] text-text-faint">Avg Own%</div>
                  <div className="text-sm text-text">{fmt(s.averageOwnership)}</div>
                </div>
                <div>
                  <div className="text-[10px] text-text-faint">Team Popularity</div>
                  <div className="text-sm text-text">{fmt(s.teamPopularityScore)}</div>
                </div>
                <div>
                  <div className="text-[10px] text-text-faint">Avg Power</div>
                  <div className="text-sm text-text">{fmt(s.averagePower)}</div>
                </div>
                <div>
                  <div className="text-[10px] text-text-faint">Avg Confidence</div>
                  <div className="text-sm text-text">{fmt(s.averageConfidence)}</div>
                </div>
              </div>
              <div className="border-t border-border-subtle pt-2">
                <div className="mb-1 text-[10px] uppercase text-text-faint">Top 5 Projected</div>
                <ul className="text-xs text-text-muted">
                  {s.top5.map((h) => (
                    <li key={h.id} className="flex justify-between py-0.5">
                      <span className="text-text">{h.name}</span>
                      <span>{fmt(h.projection)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
