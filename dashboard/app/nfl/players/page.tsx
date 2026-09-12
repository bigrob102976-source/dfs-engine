"use client";

import { NflPageShell } from "@/components/nfl/NflPageShell";
import { NflPlayerTable } from "@/components/nfl/NflPlayerTable";
import { NflStalenessBanner } from "@/components/nfl/NflStalenessBanner";
import { useNflData } from "@/lib/nfl/useNflData";
import { useNflDraftGroupId } from "@/lib/nfl/useNflDraftGroupId";

function PlayersContent() {
  const draftGroupId = useNflDraftGroupId();
  const { data, loading, error } = useNflData(draftGroupId);

  if (loading && !data) return <p className="text-sm text-text-faint">Loading real NFL player pool…</p>;
  if (error) return <p className="text-sm text-red">{error}</p>;
  if (!data) return null;

  return (
    <div className="space-y-3">
      <NflStalenessBanner data={data} />
      <NflPlayerTable players={data.players} draftGroupId={draftGroupId} variant="players" />
    </div>
  );
}

export default function NflPlayersPage() {
  return (
    <NflPageShell title="NFL Players" description="Real DraftKings NFL Classic player pool. Lock/Exclude carries into the Optimizer.">
      <PlayersContent />
    </NflPageShell>
  );
}
