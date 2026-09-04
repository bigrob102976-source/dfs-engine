"use client";

import { DataCard, MetricCard } from "@/components/ui";
import { NflPageShell } from "@/components/nfl/NflPageShell";
import { fmt } from "@/lib/nfl/format";
import { useNflData } from "@/lib/nfl/useNflData";
import { useNflDraftGroupId } from "@/lib/nfl/useNflDraftGroupId";

function OverviewContent() {
  const draftGroupId = useNflDraftGroupId();
  const { data, loading, error, refresh } = useNflData(draftGroupId);

  if (loading && !data) return <p className="text-sm text-text-faint">Loading real NFL slate data…</p>;
  if (error) return <p className="text-sm text-red">{error}</p>;
  if (!data) return null;

  const projectedTotal = Object.values(data.projection_coverage).reduce((sum, c) => sum + c.projected, 0);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <MetricCard label="Slate" value={data.slate_name ?? "--"} />
        <MetricCard label="DraftGroup" value={data.draft_group_id} />
        <MetricCard label="Games" value={data.game_count} />
        <MetricCard label="Players" value={data.player_count} />
        <MetricCard label="Salary Cap" value={`$${data.salary_cap.toLocaleString()}`} />
        <MetricCard label="Freshness" value={`${data.current_season} Wk ${data.current_week}`} />
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <MetricCard label="Identity Resolved" value={`${data.identity.resolved}/${data.identity.total}`} tone={data.identity.unresolved > 0 ? "neutral" : "positive"} />
        <MetricCard label="Projected Players" value={`${projectedTotal}/${data.player_count}`} tone="neutral" />
        <MetricCard label="Vegas" value={data.vegas_configured ? "Configured" : "Not Available"} tone={data.vegas_configured ? "positive" : "neutral"} />
      </div>

      <DataCard title="Position Counts">
        <div className="flex flex-wrap gap-4">
          {Object.entries(data.position_counts).map(([pos, count]) => (
            <div key={pos} className="text-sm">
              <span className="font-semibold text-text">{count}</span> <span className="text-text-faint">{pos}</span>
            </div>
          ))}
        </div>
      </DataCard>

      <DataCard title={`Games (${data.games.length})`} action={<button onClick={refresh} className="text-xs text-accent hover:underline">Refresh</button>}>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-border-subtle text-text-faint">
                <th className="py-2 pr-3 font-medium">Matchup</th>
                <th className="py-2 pr-3 font-medium">Kickoff</th>
                <th className="py-2 pr-3 font-medium">Total</th>
                <th className="py-2 pr-3 font-medium">Spread</th>
                <th className="py-2 pr-3 font-medium">Implied (Away / Home)</th>
              </tr>
            </thead>
            <tbody>
              {data.games.map((g) => (
                <tr key={g.game_id} className="border-b border-border-subtle/50">
                  <td className="py-2 pr-3 text-text">{g.game_description ?? "--"}</td>
                  <td className="py-2 pr-3 text-text-muted">{g.game_start_time ? new Date(g.game_start_time).toLocaleString() : "--"}</td>
                  <td className="py-2 pr-3 text-text-muted">{fmt(g.total)}</td>
                  <td className="py-2 pr-3 text-text-muted">{fmt(g.spread_home)}</td>
                  <td className="py-2 pr-3 text-text-muted">
                    {fmt(g.away_implied_total)} / {fmt(g.home_implied_total)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!data.vegas_configured && (
          <p className="mt-2 text-[11px] text-text-faint">Vegas fields show — until real odds-provider credentials are configured (see nfl/odds_provider.py).</p>
        )}
      </DataCard>
    </div>
  );
}

export default function NflOverviewPage() {
  return (
    <NflPageShell title="NFL Overview" description="Real DraftKings NFL Classic slate summary.">
      <OverviewContent />
    </NflPageShell>
  );
}
