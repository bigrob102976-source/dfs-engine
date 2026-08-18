import { MissingDataState } from "@/components/MissingDataState";
import { PlayerTable } from "@/components/PlayerTable";
import { PageHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { loadLatestDKPlayerPool, loadLatestOwnershipSnapshot, loadLatestPitcherSnapshot } from "@/lib/loaders";
import { buildPitcherRows } from "@/lib/normalize";
import { effectiveGameIds, filterByGameIds, formatSlateLabel, resolveSlateContext } from "@/lib/slateContext";

export const dynamic = "force-dynamic";

export default async function TopPitchersPage(props: PageProps<"/dashboard/pitchers">) {
  const searchParams = await props.searchParams;
  const highlightId = typeof searchParams.player === "string" ? searchParams.player : undefined;
  const team = typeof searchParams.team === "string" ? searchParams.team : undefined;
  const slateId = typeof searchParams.slate === "string" ? searchParams.slate : undefined;

  const date = getTodayChicagoDate();
  const slateCtx = await resolveSlateContext(date, slateId);
  const pitcherSnapshot = date ? loadLatestPitcherSnapshot(date).data : null;
  const ownership = date ? loadLatestOwnershipSnapshot(date, slateCtx.selected?.slateId ?? null).data : null;
  const pool = date ? loadLatestDKPlayerPool(date).data : null;

  const allRows = buildPitcherRows(pitcherSnapshot?.pitchers ?? [], ownership, pool);
  const rows = filterByGameIds(allRows, effectiveGameIds(slateCtx));

  const slateDescription = slateCtx.selected ? ` (${formatSlateLabel(slateCtx.selected)})` : "";

  return (
    <div>
      <PageHeader
        title="Top Pitchers"
        description={pitcherSnapshot ? `${rows.length} probable starters, from ${date}'s pitcher snapshot${slateDescription}.` : undefined}
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
