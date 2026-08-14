import { MissingDataState } from "@/components/MissingDataState";
import { PlayerTable } from "@/components/PlayerTable";
import { PageHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { loadLatestDKPlayerPool, loadLatestOwnershipSnapshot, loadLatestPitcherSnapshot } from "@/lib/loaders";
import { buildPitcherRows } from "@/lib/normalize";

export const dynamic = "force-dynamic";

export default async function TopPitchersPage(props: PageProps<"/dashboard/pitchers">) {
  const searchParams = await props.searchParams;
  const highlightId = typeof searchParams.player === "string" ? searchParams.player : undefined;

  const date = getTodayChicagoDate();
  const pitcherSnapshot = date ? loadLatestPitcherSnapshot(date).data : null;
  const ownership = date ? loadLatestOwnershipSnapshot(date).data : null;
  const pool = date ? loadLatestDKPlayerPool(date).data : null;

  const rows = buildPitcherRows(pitcherSnapshot?.pitchers ?? [], ownership, pool);

  return (
    <div>
      <PageHeader
        title="Top Pitchers"
        description={pitcherSnapshot ? `${rows.length} probable starters, from ${date}'s pitcher snapshot.` : undefined}
      />
      {pitcherSnapshot ? (
        <PlayerTable rows={rows} variant="pitcher" initialSortKey="projection" highlightId={highlightId} />
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
