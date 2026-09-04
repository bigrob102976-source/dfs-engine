"use client";

import { DataCard } from "@/components/ui";
import { NflPageShell } from "@/components/nfl/NflPageShell";
import { NflPlayerTable } from "@/components/nfl/NflPlayerTable";
import { fmt } from "@/lib/nfl/format";
import { useNflData } from "@/lib/nfl/useNflData";
import { useNflDraftGroupId } from "@/lib/nfl/useNflDraftGroupId";
import type { NflPlayerRow } from "@/lib/nfl/types";

// NFL UI M1 -- position-aware detailed usage fields (M8's real
// rolling_features/season_to_date_features keys). Only fields that
// genuinely exist are read; routes are never approximated -- see
// historical_nfl/usage_normalize.py's own module docstring.
const FIELDS_BY_POSITION: Record<string, { key: string; label: string }[]> = {
  QB: [
    { key: "pass_attempts_mean_last3", label: "Attempts (L3)" },
    { key: "completions_mean_last3", label: "Completions (L3)" },
    { key: "passing_yards_mean_last3", label: "Pass Yds (L3)" },
    { key: "carries_mean_last3", label: "Rush Att (L3)" },
  ],
  RB: [
    { key: "offensive_snaps_mean_last3", label: "Snaps (L3)" },
    { key: "snap_share_mean_last3", label: "Snap % (L3)" },
    { key: "carries_mean_last3", label: "Carries (L3)" },
    { key: "carry_share_mean_last3", label: "Carry Share (L3)" },
    { key: "targets_mean_last3", label: "Targets (L3)" },
    { key: "red_zone_carries_mean_last3", label: "RZ Carries (L3)" },
    { key: "goal_line_carries_mean_last3", label: "GL Carries (L3)" },
  ],
  WR: [
    { key: "offensive_snaps_mean_last3", label: "Snaps (L3)" },
    { key: "snap_share_mean_last3", label: "Snap % (L3)" },
    { key: "targets_mean_last3", label: "Targets (L3)" },
    { key: "target_share_mean_last3", label: "Target Share (L3)" },
    { key: "receptions_mean_last3", label: "Receptions (L3)" },
    { key: "red_zone_targets_mean_last3", label: "RZ Targets (L3)" },
  ],
  DST: [
    { key: "sacks_mean_last3", label: "Sacks (L3)" },
    { key: "interceptions_mean_last3", label: "INT (L3)" },
    { key: "defensive_tds_mean_last3", label: "Def TD (L3)" },
    { key: "points_allowed_mean_last3", label: "Points Allowed (L3)" },
    { key: "yards_allowed_mean_last3", label: "Yards Allowed (L3)" },
  ],
};
FIELDS_BY_POSITION.TE = FIELDS_BY_POSITION.WR;

function UsageContent() {
  const draftGroupId = useNflDraftGroupId();
  const { data, loading, error } = useNflData(draftGroupId);
  const searchInput = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
  const selectedId = searchInput?.get("player");

  if (loading && !data) return <p className="text-sm text-text-faint">Loading real NFL usage data…</p>;
  if (error) return <p className="text-sm text-red">{error}</p>;
  if (!data) return null;

  const selected: NflPlayerRow | undefined = data.players.find((p) => p.draftkings_player_id === selectedId);

  return (
    <div className="space-y-4">
      {selected && (
        <DataCard title={`${selected.name} -- Recent Trend (Last 1 / 3 / 5)`}>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {(FIELDS_BY_POSITION[selected.is_team_entity ? "DST" : selected.position] ?? []).map((f) => {
              const base = f.key.replace("_mean_last3", "");
              return (
                <div key={f.key} className="rounded-[var(--radius-control)] border border-border-subtle p-2 text-xs">
                  <div className="text-text-faint">{f.label.replace(" (L3)", "")}</div>
                  <div className="mt-1 flex gap-2 text-text">
                    <span>L1: {fmt(selected.usage?.rolling[`${base}_mean_last1`])}</span>
                    <span>L3: {fmt(selected.usage?.rolling[`${base}_mean_last3`])}</span>
                    <span>L5: {fmt(selected.usage?.rolling[`${base}_mean_last5`])}</span>
                  </div>
                </div>
              );
            })}
          </div>
          <p className="mt-2 text-[11px] text-text-faint">Route participation: Not Available (see historical_nfl/usage_normalize.py -- real source data does not support per-player route attribution).</p>
        </DataCard>
      )}
      <NflPlayerTable players={data.players} draftGroupId={draftGroupId} variant="usage" />
    </div>
  );
}

export default function NflUsagePage() {
  return (
    <NflPageShell title="NFL Usage" description="Real historical usage (M8): snaps, shares, red-zone/goal-line, recent trends.">
      <UsageContent />
    </NflPageShell>
  );
}
