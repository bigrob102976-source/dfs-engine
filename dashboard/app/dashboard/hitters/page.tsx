import { EligibilityFilterSelect } from "@/components/EligibilityFilterSelect";
import { MissingDataState } from "@/components/MissingDataState";
import { PlayerTable } from "@/components/PlayerTable";
import { PageHeader } from "@/components/ui/Header";
import { getBlueCollarProjectionByPlayerId } from "@/lib/blueCollarProjections";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { HITTER_ELIGIBILITY_OPTIONS, filterHitterRowsByEligibility, isHitterEligibilityFilter } from "@/lib/eligibilityFilter";
import { loadLatestDKPlayerPool, loadLatestOwnershipSnapshot, loadLatestBatterSnapshot } from "@/lib/loaders";
import { getMlProjectionByPlayerId } from "@/lib/mlProjections";
import { buildHitterRows } from "@/lib/normalize";
import { effectiveGameIds, filterByGameIds, formatSlateLabel, resolveSlateContext } from "@/lib/slateContext";

export const dynamic = "force-dynamic";

export default async function TopHittersPage(props: PageProps<"/dashboard/hitters">) {
  const searchParams = await props.searchParams;
  const highlightId = typeof searchParams.player === "string" ? searchParams.player : undefined;
  const team = typeof searchParams.team === "string" ? searchParams.team : undefined;
  const slateId = typeof searchParams.slate === "string" ? searchParams.slate : undefined;
  // Milestone 30.1: default view is CONFIRMED starting-lineup hitters
  // only. Bench/unconfirmed hitters never mix into the primary rankings
  // -- unconfirmed ones get their own "Waiting For Lineups" section below.
  const eligibilityParam = typeof searchParams.eligibility === "string" ? searchParams.eligibility : undefined;
  const eligibility = isHitterEligibilityFilter(eligibilityParam) ? eligibilityParam : "confirmed";

  const date = getTodayChicagoDate();
  const slateCtx = await resolveSlateContext(date, slateId);
  const [batterLoaded, ownershipLoaded, poolLoaded, mlByPlayerId, blueCollarByPlayerId] = await Promise.all([
    date ? loadLatestBatterSnapshot(date) : null,
    date ? loadLatestOwnershipSnapshot(date, slateCtx.selected?.slateId ?? null) : null,
    date ? loadLatestDKPlayerPool(date, slateCtx.selected?.slateId ?? null) : null,
    // Milestone 32.3B: Big Money ML -- independent SHADOW comparison
    // column only. Never changes eligibility/rows/default ranking.
    date ? getMlProjectionByPlayerId(date) : new Map(),
    // BlueCollar Live Projection Integration: optional comparison column.
    // Slate-scoped (see lib/blueCollarProjections.ts) -- never date-only.
    date ? getBlueCollarProjectionByPlayerId(date, slateCtx.selected?.slateId ?? null) : new Map(),
  ]);
  const batterSnapshot = batterLoaded?.data ?? null;
  const ownership = ownershipLoaded?.data ?? null;
  const pool = poolLoaded?.data ?? null;

  const allRows = buildHitterRows(batterSnapshot?.hitters ?? [], ownership, pool, mlByPlayerId, blueCollarByPlayerId);
  const gameFiltered = filterByGameIds(allRows, effectiveGameIds(slateCtx));
  const rows = filterHitterRowsByEligibility(gameFiltered, eligibility);
  const waitingRows = eligibility === "confirmed" ? filterHitterRowsByEligibility(gameFiltered, "unconfirmed") : [];
  const slateDescription = slateCtx.selected ? ` (${formatSlateLabel(slateCtx.selected)})` : "";

  return (
    <div>
      <PageHeader
        title="Top Hitters"
        description={batterSnapshot ? `${rows.length} shown, from ${date}'s batter snapshot${slateDescription}.` : undefined}
        actions={<EligibilityFilterSelect paramName="eligibility" value={eligibility} options={HITTER_ELIGIBILITY_OPTIONS} />}
      />
      {batterSnapshot ? (
        <>
          <PlayerTable rows={rows} variant="hitter" initialSortKey="projection" highlightId={highlightId} initialFilters={team ? { team } : undefined} />
          {waitingRows.length > 0 && (
            <div className="mt-4">
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">
                Waiting For Lineups ({waitingRows.length})
              </h2>
              <PlayerTable rows={waitingRows} variant="hitter" initialSortKey="salary" />
            </div>
          )}
        </>
      ) : (
        <MissingDataState
          title="Batter research is not ready for today's slate"
          description="Generate today's hitter research to view projections and Statcast analysis."
          primaryActionLabel="Generate Batter Research"
          targetSteps={["batters"]}
        />
      )}
    </div>
  );
}
