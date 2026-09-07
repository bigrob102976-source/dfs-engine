"use client";

import { DataCard } from "@/components/ui";
import { NflPageShell } from "@/components/nfl/NflPageShell";
import { NflPlayerTable } from "@/components/nfl/NflPlayerTable";
import { fmt } from "@/lib/nfl/format";
import { useNflData } from "@/lib/nfl/useNflData";
import { useNflDraftGroupId } from "@/lib/nfl/useNflDraftGroupId";

function MatchupsContent() {
  const draftGroupId = useNflDraftGroupId();
  const { data, loading, error } = useNflData(draftGroupId);

  if (loading && !data) return <p className="text-sm text-text-faint">Loading real NFL matchup context…</p>;
  if (error) return <p className="text-sm text-red">{error}</p>;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <DataCard title="Games">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-border-subtle text-text-faint">
                <th className="py-2 pr-3 font-medium">Matchup</th>
                <th className="py-2 pr-3 font-medium">Kickoff</th>
                <th className="py-2 pr-3 font-medium">Game Total</th>
                <th className="py-2 pr-3 font-medium">Spread (Home)</th>
                <th className="py-2 pr-3 font-medium">Away Implied</th>
                <th className="py-2 pr-3 font-medium">Home Implied</th>
              </tr>
            </thead>
            <tbody>
              {data.games.map((g) => (
                <tr key={g.game_id} className="border-b border-border-subtle/50">
                  <td className="py-2 pr-3 text-text">{g.game_description ?? "--"}</td>
                  <td className="py-2 pr-3 text-text-muted">{g.game_start_time ? new Date(g.game_start_time).toLocaleString() : "--"}</td>
                  <td className="py-2 pr-3 text-text-muted">{fmt(g.total)}</td>
                  <td className="py-2 pr-3 text-text-muted">{fmt(g.spread_home)}</td>
                  <td className="py-2 pr-3 text-text-muted">{fmt(g.away_implied_total)}</td>
                  <td className="py-2 pr-3 text-text-muted">{fmt(g.home_implied_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!data.vegas_configured && (
          <p className="mt-2 text-[11px] text-text-faint">
            Vegas source: {data.vegas_source_provenance} -- shown as — until real odds-provider credentials exist (nfl/odds_provider.py). Never fabricated.
          </p>
        )}
      </DataCard>

      <DataCard title="Player Matchup / Opponent Context">
        <p className="mb-2 text-[11px] text-text-faint">
          DST rows include real opponent offensive trailing form (M11: points scored, yards, sacks allowed). Offensive players show real spread/total only -- no invented
          defense-vs-position metrics.
        </p>
        <NflPlayerTable players={data.players} draftGroupId={draftGroupId} variant="matchups" />
      </DataCard>
    </div>
  );
}

export default function NflMatchupsPage() {
  return (
    <NflPageShell title="NFL Matchups" description="Real game/opponent context. Vegas fields show — until real credentials exist.">
      <MatchupsContent />
    </NflPageShell>
  );
}
