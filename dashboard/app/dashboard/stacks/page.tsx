import Link from "next/link";

import { MissingDataState } from "@/components/MissingDataState";
import { PageHeader } from "@/components/ui/Header";
import { getTodayEasternDate } from "@/lib/currentDate";
import { loadLatestDKPlayerPool, loadLatestOwnershipSnapshot, loadLatestBatterSnapshot } from "@/lib/loaders";
import { buildHitterRows } from "@/lib/normalize";
import { effectiveGameIds, filterByGameIds, formatSlateLabel, resolveSlateContext } from "@/lib/slateContext";
import { buildStackSummaries } from "@/lib/stacks";

export const dynamic = "force-dynamic";

function fmt(v: number | null): string {
  return v === null ? "--" : v.toFixed(1);
}

/** Milestone 32.6 Part 4: "USE THIS STACK" hands off a TEAM STACK RULE
 * only (stackTeam + stackSize) -- never specific locked players, since
 * this page's stacks are a team-level recommendation, not an exact
 * lineup. Preserves the current global slate; the Optimizer's own
 * Projection Source is preserved automatically too, since
 * OptimizerWorkspace always hydrates it from localStorage regardless of
 * how the page was reached (see workspaceStorage.ts). */
function buildUseThisStackHref(team: string, size: number, slateId: string | undefined): string {
  const params = new URLSearchParams();
  if (slateId) params.set("slate", slateId);
  params.set("stackTeam", team);
  params.set("stackSize", String(size));
  return `/dashboard/optimizer?${params.toString()}`;
}

export default async function StacksPage(props: PageProps<"/dashboard/stacks">) {
  const searchParams = await props.searchParams;
  const slateId = typeof searchParams.slate === "string" ? searchParams.slate : undefined;

  const date = getTodayEasternDate();
  const slateCtx = await resolveSlateContext(date, slateId);
  const [batterLoaded, ownershipLoaded, dkPoolLoaded] = await Promise.all([
    date ? loadLatestBatterSnapshot(date) : null,
    date ? loadLatestOwnershipSnapshot(date, slateCtx.selected?.slateId ?? null) : null,
    // Milestone 27.2: without the real DK pool, a team whose lineup hasn't
    // posted yet is invisible here even though its Stack Environment
    // Score (a game-level, Vegas/park/weather-driven signal) can still
    // rank #1 -- exactly the reported inconsistency. See lib/normalize.ts.
    date ? loadLatestDKPlayerPool(date, slateCtx.selected?.slateId ?? null) : null,
  ]);
  const batterSnapshot = batterLoaded?.data ?? null;
  const ownership = ownershipLoaded?.data ?? null;
  const dkPool = dkPoolLoaded?.data ?? null;

  const allRows = buildHitterRows(batterSnapshot?.hitters ?? [], ownership, dkPool);
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
              <div className="mb-3 flex items-center justify-between gap-2">
                <span className="text-sm font-semibold text-text">
                  {s.team}
                  {s.status === "CONFIRMED" && s.confirmedHitterCount >= 2 && (
                    <span className="ml-1.5 text-[11px] font-normal text-text-faint">{Math.min(5, s.confirmedHitterCount)}-MAN STACK</span>
                  )}
                </span>
                {s.status === "CONFIRMED" && s.confirmedHitterCount >= 2 && (
                  <Link
                    href={buildUseThisStackHref(s.team, Math.min(5, s.confirmedHitterCount), slateCtx.selected?.slateId)}
                    className="rounded bg-accent-dim px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-accent hover:bg-accent/20"
                  >
                    Use This Stack
                  </Link>
                )}
              </div>
              <div className="mb-3 flex items-center justify-end">
                <span className="text-[11px] text-text-faint">
                  {s.status === "WAITING_FOR_LINEUP" ? (
                    <span className="font-semibold uppercase text-yellow">Waiting For Lineup</span>
                  ) : (
                    <>
                      {s.confirmedHitterCount} / {s.totalHitterCount} confirmed
                      {s.confirmedHitterCount < s.totalHitterCount && <span className="ml-1 text-yellow">({s.totalHitterCount - s.confirmedHitterCount} bench/unconfirmed)</span>}
                    </>
                  )}
                </span>
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
                <div className="mb-1 text-[10px] uppercase text-text-faint">Top 5 Confirmed Starters (by Projection, then Salary)</div>
                {s.top5.length === 0 ? (
                  <p className="py-1 text-xs text-text-faint">No confirmed starting lineup yet -- check back once it posts.</p>
                ) : (
                  <ul className="text-xs text-text-muted">
                    {s.top5.map((h) => (
                      <li key={h.id} className="flex justify-between py-0.5">
                        <span className="text-text">{h.name}</span>
                        <span>{h.projection !== null ? fmt(h.projection) : `$${h.salary?.toLocaleString() ?? "--"}`}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
