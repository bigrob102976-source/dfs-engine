import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { loadLatestOwnershipSnapshot } from "@/lib/loaders";

export const dynamic = "force-dynamic";

function fmt(v: number | null | undefined, digits = 1): string {
  return v === null || v === undefined ? "--" : v.toFixed(digits);
}

/** Ownership leaderboard: today's projected-ownership snapshot, sorted
 * highest-owned first, with each player's leverage score alongside so
 * chalk and contrarian plays are visible at a glance. Read-only --
 * ownership projections themselves are computed entirely by
 * ownership/ (Milestone 9/10), never recomputed here. */
export default function OwnershipPage() {
  const date = getTodayChicagoDate();
  const snapshot = loadLatestOwnershipSnapshot(date).data;

  return (
    <div>
      <PageHeader title="Ownership" description={snapshot ? `Projected ownership for ${date}'s slate.` : undefined} />

      {!snapshot ? (
        <EmptyState
          icon="🧠"
          title="Ownership projections are not ready for today's slate"
          description="Ownership is generated once the player pool exists -- refresh today's slate from the main dashboard to build it."
        />
      ) : (
        <div className="overflow-hidden rounded-[var(--radius-card)] border border-border shadow-[var(--shadow-card)]">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-bg-panel-raised">
              <tr>
                <th className="px-3 py-2 text-left text-[11px] uppercase tracking-wide text-text-faint">Player</th>
                <th className="px-3 py-2 text-left text-[11px] uppercase tracking-wide text-text-faint">Team</th>
                <th className="px-3 py-2 text-right text-[11px] uppercase tracking-wide text-text-faint">Salary</th>
                <th className="px-3 py-2 text-right text-[11px] uppercase tracking-wide text-text-faint">Proj</th>
                <th className="px-3 py-2 text-right text-[11px] uppercase tracking-wide text-text-faint">Own%</th>
                <th className="px-3 py-2 text-right text-[11px] uppercase tracking-wide text-text-faint">Leverage</th>
              </tr>
            </thead>
            <tbody className="bg-bg-panel">
              {[...snapshot.players]
                .sort((a, b) => b.projected_ownership - a.projected_ownership)
                .map((p) => (
                  <tr key={p.dk_player_id} className="border-t border-border-subtle hover:bg-bg-panel-raised">
                    <td className="px-3 py-2 font-medium text-text">{p.name}</td>
                    <td className="px-3 py-2 text-text-muted">{p.team}</td>
                    <td className="px-3 py-2 text-right text-text">${p.salary.toLocaleString()}</td>
                    <td className="px-3 py-2 text-right text-text">{fmt(p.projection)}</td>
                    <td className="px-3 py-2 text-right font-semibold text-yellow">{fmt(p.projected_ownership)}%</td>
                    <td className={`px-3 py-2 text-right font-semibold ${p.leverage_score >= 0 ? "text-green" : "text-red"}`}>
                      {p.leverage_score >= 0 ? "+" : ""}
                      {fmt(p.leverage_score)}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
