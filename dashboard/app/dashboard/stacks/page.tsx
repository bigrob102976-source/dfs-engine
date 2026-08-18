import { MissingDataState } from "@/components/MissingDataState";
import { PageHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { loadLatestOwnershipSnapshot, loadLatestBatterSnapshot } from "@/lib/loaders";
import { buildHitterRows } from "@/lib/normalize";
import { effectiveGameIds, filterByGameIds, formatSlateLabel, resolveSlateContext } from "@/lib/slateContext";
import { buildStackSummaries } from "@/lib/stacks";

export const dynamic = "force-dynamic";

function fmt(v: number | null): string {
  return v === null ? "--" : v.toFixed(1);
}

export default async function StacksPage(props: PageProps<"/dashboard/stacks">) {
  const searchParams = await props.searchParams;
  const slateId = typeof searchParams.slate === "string" ? searchParams.slate : undefined;

  const date = getTodayChicagoDate();
  const slateCtx = await resolveSlateContext(date, slateId);
  const batterSnapshot = date ? loadLatestBatterSnapshot(date).data : null;
  const ownership = date ? loadLatestOwnershipSnapshot(date, slateCtx.selected?.slateId ?? null).data : null;

  const allRows = buildHitterRows(batterSnapshot?.hitters ?? [], ownership, null);
  const rows = filterByGameIds(allRows, effectiveGameIds(slateCtx));
  const stacks = buildStackSummaries(rows, ownership?.team_popularity ?? {});
  const slateDescription = slateCtx.selected ? ` -- ${formatSlateLabel(slateCtx.selected)}` : "";

  return (
    <div>
      <PageHeader
        title="Stacks"
        description={`Existing per-team data summarized -- no simulation. Team Popularity requires an ownership snapshot to be loaded.${slateDescription}`}
      />

      {!batterSnapshot ? (
        <MissingDataState
          title="Stack data is not ready for today's slate"
          description="Generate today's hitter research to view team stacks and popularity."
          primaryActionLabel="Refresh Required Data"
          targetSteps={["batters"]}
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {stacks.map((s) => (
            <div key={s.team} className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
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
