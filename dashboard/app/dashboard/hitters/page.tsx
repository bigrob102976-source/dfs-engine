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
      <p className="mb-4 text-xs text-text-faint">
        {batterSnapshot
          ? `${rows.length} confirmed starting-lineup hitters, from ${date}'s batter snapshot.`
          : "Batter snapshot not generated yet."}
      </p>
      {batterSnapshot ? (
        <PlayerTable rows={rows} variant="hitter" initialSortKey="projection" highlightId={highlightId} />
      ) : (
        <div className="rounded border border-border bg-bg-panel p-6 text-sm text-text-faint">
          Run: <code className="text-text-muted">python scripts/run_real_batter_agent.py --date {date ?? "YYYY-MM-DD"}</code>
        </div>
      )}
    </div>
  );
}
