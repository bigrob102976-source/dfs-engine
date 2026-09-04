"use client";

import { MetricCard } from "@/components/ui";
import { NflPageShell } from "@/components/nfl/NflPageShell";
import { NflPlayerTable } from "@/components/nfl/NflPlayerTable";
import { useNflData } from "@/lib/nfl/useNflData";
import { useNflDraftGroupId } from "@/lib/nfl/useNflDraftGroupId";

function ProjectionsContent() {
  const draftGroupId = useNflDraftGroupId();
  const { data, loading, error } = useNflData(draftGroupId);

  if (loading && !data) return <p className="text-sm text-text-faint">Loading real Big Money Native projections…</p>;
  if (error) return <p className="text-sm text-red">{error}</p>;
  if (!data) return null;

  return (
    <div className="space-y-4">
      {data.projection_error && (
        <p className="rounded-[var(--radius-control)] border border-yellow/40 bg-yellow/10 p-2 text-xs text-yellow">
          Projections unavailable: {data.projection_error}
        </p>
      )}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {(["QB", "RB", "WR", "TE", "DST"] as const).map((pos) => {
          const c = data.projection_coverage[pos];
          return <MetricCard key={pos} label={`${pos} Coverage`} value={c ? `${c.projected}/${c.total}` : "0/0"} />;
        })}
      </div>
      <div className="flex gap-4 text-xs text-text-faint">
        <span>Resolved identity: {data.identity.resolved}</span>
        <span>Unresolved identity: {data.identity.unresolved}</span>
      </div>
      <NflPlayerTable players={data.players} draftGroupId={draftGroupId} variant="projections" />
    </div>
  );
}

export default function NflProjectionsPage() {
  return (
    <NflPageShell title="NFL Projections" description="Real Big Money Native projections. DST honestly labeled when using the baseline fallback.">
      <ProjectionsContent />
    </NflPageShell>
  );
}
