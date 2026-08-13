import { MissingDataState } from "@/components/MissingDataState";
import { PlayerTable } from "@/components/PlayerTable";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { loadLatestDKPlayerPool, loadLatestOwnershipSnapshot, loadLatestBatterSnapshot } from "@/lib/loaders";
import { buildHitterRows } from "@/lib/normalize";

export const dynamic = "force-dynamic";

export default async function TopHittersPage(props: PageProps<"/dashboard/hitters">) {
  const searchParams = await props.searchParams;
  const highlightId = typeof searchParams.player === "string" ? searchParams.player : undefined;

  const date = getTodayChicagoDate();
  const batterSnapshot = date ? loadLatestBatterSnapshot(date).data : null;
  const ownership = date ? loadLatestOwnershipSnapshot(date).data : null;
  const pool = date ? loadLatestDKPlayerPool(date).data : null;

  const rows = buildHitterRows(batterSnapshot?.hitters ?? [], ownership, pool);

  return (
    <div>
      <h1 className="mb-1 text-lg font-semibold text-text">Top Hitters</h1>
      {batterSnapshot && (
        <p className="mb-4 text-xs text-text-faint">
          {rows.length} confirmed starting-lineup hitters, from {date}&apos;s batter snapshot.
        </p>
      )}
      {batterSnapshot ? (
        <PlayerTable rows={rows} variant="hitter" initialSortKey="projection" highlightId={highlightId} />
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
