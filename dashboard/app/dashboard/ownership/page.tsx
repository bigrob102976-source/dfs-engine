import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { loadLatestOwnershipSnapshot } from "@/lib/loaders";
import { formatSlateLabel, resolveSlateContext } from "@/lib/slateContext";

export const dynamic = "force-dynamic";

function fmt(v: number | null | undefined, digits = 1): string {
  return v === null || v === undefined ? "--" : v.toFixed(digits);
}

/** Ownership leaderboard: today's projected-ownership snapshot, sorted
 * highest-owned first, with each player's leverage score alongside so
 * chalk and contrarian plays are visible at a glance. Read-only --
 * ownership projections themselves are computed entirely by
 * ownership/ (Milestone 9/10), never recomputed here.
 *
 * Milestone 26: ownership is inherently SLATE-RELATIVE (a $9,500 pitcher
 * means something different on a 3-game Turbo slate than a 9-game Main
 * slate -- see ownership/slate_normalization.py) -- when a slate is
 * selected, this reads that slate's own ownership_predictions/<date>/
 * <slateId>/ snapshot, never another slate's or a stale merged one. */
export default async function OwnershipPage(props: PageProps<"/dashboard/ownership">) {
  const searchParams = await props.searchParams;
  const slateId = typeof searchParams.slate === "string" ? searchParams.slate : undefined;

  const date = getTodayChicagoDate();
  const slateCtx = await resolveSlateContext(date, slateId);
  const snapshot = loadLatestOwnershipSnapshot(date, slateCtx.selected?.slateId ?? null).data;
  const slateDescription = slateCtx.selected ? ` (${formatSlateLabel(slateCtx.selected)})` : "";

  return (
    <div>
      <PageHeader title="Ownership" description={snapshot ? `Projected ownership for ${date}'s slate${slateDescription}.` : undefined} />

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
