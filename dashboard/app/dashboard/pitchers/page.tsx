import { EligibilityFilterSelect } from "@/components/EligibilityFilterSelect";
import { MissingDataState } from "@/components/MissingDataState";
import { PlayerTable } from "@/components/PlayerTable";
import { PageHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { PITCHER_ELIGIBILITY_OPTIONS, filterPitcherRowsByEligibility, isPitcherEligibilityFilter } from "@/lib/eligibilityFilter";
import { loadLatestDKPlayerPool, loadLatestOwnershipSnapshot, loadLatestPitcherSnapshot } from "@/lib/loaders";
import { buildPitcherRows } from "@/lib/normalize";
import { effectiveGameIds, filterByGameIds, formatSlateLabel, resolveSlateContext } from "@/lib/slateContext";

export const dynamic = "force-dynamic";

export default async function TopPitchersPage(props: PageProps<"/dashboard/pitchers">) {
  const searchParams = await props.searchParams;
  const highlightId = typeof searchParams.player === "string" ? searchParams.player : undefined;
  const team = typeof searchParams.team === "string" ? searchParams.team : undefined;
  const slateId = typeof searchParams.slate === "string" ? searchParams.slate : undefined;
  // Milestone 30.1: default view is confirmed/probable STARTING PITCHERS
  // only -- relief pitchers no longer clutter the normal DFS experience.
  // "All DK Pitchers"/"Relief"/"Unmatched" are opt-in via this filter.
  const eligibilityParam = typeof searchParams.eligibility === "string" ? searchParams.eligibility : undefined;
  const eligibility = isPitcherEligibilityFilter(eligibilityParam) ? eligibilityParam : "starting";

  const date = getTodayChicagoDate();
  const slateCtx = await resolveSlateContext(date, slateId);
  const pitcherSnapshot = date ? loadLatestPitcherSnapshot(date).data : null;
  const ownership = date ? loadLatestOwnershipSnapshot(date, slateCtx.selected?.slateId ?? null).data : null;
  const pool = date ? loadLatestDKPlayerPool(date, slateCtx.selected?.slateId ?? null).data : null;

  const allRows = buildPitcherRows(pitcherSnapshot?.pitchers ?? [], ownership, pool);
  const gameFiltered = filterByGameIds(allRows, effectiveGameIds(slateCtx));
  const rows = filterPitcherRowsByEligibility(gameFiltered, eligibility);

  const slateDescription = slateCtx.selected ? ` (${formatSlateLabel(slateCtx.selected)})` : "";

  return (
    <div>
      <PageHeader
        title="Top Pitchers"
        description={pitcherSnapshot ? `${rows.length} shown, from ${date}'s pitcher snapshot${slateDescription}.` : undefined}
        actions={<EligibilityFilterSelect paramName="eligibility" value={eligibility} options={PITCHER_ELIGIBILITY_OPTIONS} />}
      />
      {pitcherSnapshot ? (
        <PlayerTable rows={rows} variant="pitcher" initialSortKey="projection" highlightId={highlightId} initialFilters={team ? { team } : undefined} />
      ) : (
        <MissingDataState
          title="Pitcher research is not ready for today's slate"
          description="Generate today's pitcher research to view projections and matchup analysis."
          primaryActionLabel="Generate Pitcher Research"
          targetSteps={["pitchers"]}
        />
      )}
    </div>
  );
}
