import { PlayerTable } from "@/components/PlayerTable";
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
      <h1 className="mb-1 text-lg font-semibold text-text">Top Pitchers</h1>
      <p className="mb-4 text-xs text-text-faint">
        {pitcherSnapshot ? `${rows.length} probable starters, from ${date}'s pitcher snapshot.` : "Pitcher snapshot not generated yet."}
      </p>
      {pitcherSnapshot ? (
        <PlayerTable rows={rows} variant="pitcher" initialSortKey="projection" highlightId={highlightId} />
      ) : (
        <div className="rounded border border-border bg-bg-panel p-6 text-sm text-text-faint">
          Run: <code className="text-text-muted">python scripts/run_real_pitcher_agent.py --date {date ?? "YYYY-MM-DD"}</code>
        </div>
      )}
    </div>
  );
}
