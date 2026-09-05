"use client";

import { useState } from "react";

import { DataCard, PrimaryButton } from "@/components/ui";
import { NflPageShell } from "@/components/nfl/NflPageShell";
import { NFL_ROSTER_SLOT_ORDER, type NflLineup } from "@/lib/nfl/types";
import { fmtSalary, fmt, fmtOwnership } from "@/lib/nfl/format";
import { loadOptimizeResult } from "@/lib/nfl/optimizeResultStorage";
import { useNflData } from "@/lib/nfl/useNflData";
import { useNflDraftGroupId } from "@/lib/nfl/useNflDraftGroupId";

function LineupsContent() {
  const draftGroupId = useNflDraftGroupId();
  const [result] = useState(() => loadOptimizeResult(draftGroupId));
  const { data } = useNflData(draftGroupId);
  const [savingIndex, setSavingIndex] = useState<number | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  if (!result) {
    return (
      <p className="text-sm text-text-faint">
        No lineups built yet for this slate. Go to the Optimizer tab, set Lock/Exclude and lineup count, then Build Lineups.
      </p>
    );
  }

  async function saveLineup(lineup: NflLineup) {
    if (!data) return;
    setSavingIndex(lineup.index);
    setSaveMessage(null);
    try {
      const byId = new Map(data.players.map((p) => [p.draftkings_player_id, p]));
      const slots = NFL_ROSTER_SLOT_ORDER.map((slot) => {
        const a = lineup.assignments.find((x) => x.slot === slot);
        if (!a) return null;
        const p = byId.get(a.draftkings_player_id);
        return {
          roster_slot: slot, draftkings_player_id: a.draftkings_player_id, name: a.name, team: a.team,
          opponent: p?.opponent ?? null, game_id: p?.game_id ?? "", game_start_utc: p?.game_lock?.start_time_utc ?? null,
          position: a.position, salary: a.salary,
          projection_snapshot: p?.projection?.projection ?? null, ceiling_snapshot: a.ceiling, ownership_snapshot: a.projected_ownership,
        };
      });
      if (slots.some((s) => s === null)) {
        setSaveMessage(`Lineup ${lineup.index + 1}: cannot save -- missing a roster slot.`);
        return;
      }
      const res = await fetch("/api/nfl/lineups", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ draftGroupId, slateDate: data.slate_date, mode: result!.mode, stackConfig: {}, slots }),
      });
      const json = await res.json();
      if (!res.ok || json.error) {
        setSaveMessage(`Lineup ${lineup.index + 1}: ${json.error || "save failed."}`);
        return;
      }
      setSaveMessage(`Lineup ${lineup.index + 1} saved -- open it on the Saved / Late Swap tab.`);
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : "Unknown error saving lineup.");
    } finally {
      setSavingIndex(null);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-text-muted">
        Generated {result.generated} / {result.requested} lineup(s) -- mode: {result.mode}
        {result.stopped_reason && <span className="ml-2 text-yellow">{result.stopped_reason}</span>}
      </p>
      {saveMessage && <p className="text-xs text-accent">{saveMessage}</p>}
      {result.lineups.map((lineup) => (
        <DataCard key={lineup.index} title={`Lineup ${lineup.index + 1}`}>
          <div className="mb-2 flex flex-wrap items-center gap-4 text-xs text-text-muted">
            <span>
              Total Salary: <span className="font-semibold text-text">{fmtSalary(lineup.total_salary)}</span>
            </span>
            <span>
              Remaining Salary: <span className="font-semibold text-text">{fmtSalary(lineup.remaining_salary)}</span>
            </span>
            {lineup.total_projection !== null && (
              <span>
                Total Projection: <span className="font-semibold text-text">{fmt(lineup.total_projection)}</span>
              </span>
            )}
            {lineup.total_ceiling !== null && (
              <span>
                Total Ceiling: <span className="font-semibold text-text">{fmt(lineup.total_ceiling)}</span>
              </span>
            )}
            {lineup.sum_ownership !== null && (
              <span>
                Sum Ownership: <span className="font-semibold text-text">{fmtOwnership(lineup.sum_ownership)}</span>
              </span>
            )}
            {lineup.average_ownership !== null && (
              <span>
                Avg Ownership: <span className="font-semibold text-text">{fmtOwnership(lineup.average_ownership)}</span>
              </span>
            )}
            {result.mode === "leverage" && lineup.total_leverage_score !== null && (
              <span>
                Total Leverage: <span className="font-semibold text-text">{fmt(lineup.total_leverage_score)}</span>
              </span>
            )}
            <PrimaryButton onClick={() => saveLineup(lineup)} disabled={!data || savingIndex === lineup.index} className="ml-auto px-2 py-1 text-[11px]">
              {savingIndex === lineup.index ? "Saving…" : "Save Lineup"}
            </PrimaryButton>
          </div>
          {(lineup.qb_stack_team || lineup.bring_back_player || lineup.rb_dst_team) && (
            <div className="mb-2 flex flex-wrap gap-2 text-[11px]">
              {lineup.qb_stack_team && (
                <span className="rounded-[var(--radius-control)] border border-accent/40 bg-accent/10 px-2 py-0.5 text-accent">
                  QB Stack: {lineup.qb_stack_team} ({lineup.qb_stack_receiver_count} receiver{lineup.qb_stack_receiver_count === 1 ? "" : "s"})
                </span>
              )}
              {lineup.bring_back_player && (
                <span className="rounded-[var(--radius-control)] border border-gold/40 bg-gold/10 px-2 py-0.5 text-gold">
                  Bring Back: {lineup.bring_back_player}
                </span>
              )}
              {lineup.rb_dst_team && (
                <span className="rounded-[var(--radius-control)] border border-border-subtle bg-bg-panel-raised px-2 py-0.5 text-text-muted">
                  RB+DST: {lineup.rb_dst_team}
                </span>
              )}
            </div>
          )}
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-border-subtle text-text-faint">
                <th className="py-1.5 pr-3 font-medium">Slot</th>
                <th className="py-1.5 pr-3 font-medium">Player</th>
                <th className="py-1.5 pr-3 font-medium">Team</th>
                <th className="py-1.5 pr-3 font-medium">Salary</th>
                <th className="py-1.5 pr-3 font-medium">Ownership</th>
              </tr>
            </thead>
            <tbody>
              {NFL_ROSTER_SLOT_ORDER.map((slot) => {
                const a = lineup.assignments.find((x) => x.slot === slot);
                return (
                  <tr key={slot} className="border-b border-border-subtle/50">
                    <td className="py-1.5 pr-3 text-text-faint">{slot}</td>
                    <td className="py-1.5 pr-3 font-medium text-text">{a?.name ?? "--"}</td>
                    <td className="py-1.5 pr-3 text-text-muted">{a?.team ?? "--"}</td>
                    <td className="py-1.5 pr-3 text-text-muted">{a ? fmtSalary(a.salary) : "--"}</td>
                    <td className="py-1.5 pr-3 text-text-muted">{a ? fmtOwnership(a.projected_ownership) : "--"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </DataCard>
      ))}
      <p className="text-[11px] text-text-faint">
        Per-player Ownership is Big Money Native&apos;s nfl_ownership_v1 deterministic estimate (see the Players/Projections tabs) -- null/-- whenever a player has no usable
        projection, or the lineup was built in Roster Feasibility mode (which never fetches projections/ownership). Sum/Average Ownership and Total Ceiling above are only
        shown when EVERY assigned player has that real data -- never a partial or fabricated total. QB Stack/Bring Back/RB+DST badges reflect what was ACTUALLY rostered,
        independently re-derived from the lineup itself -- not just whether the setting was requested. Save Lineup persists it for game-day Late Swap (see the Saved / Late
        Swap tab).
      </p>
    </div>
  );
}

export default function NflLineupsPage() {
  return (
    <NflPageShell title="NFL Lineups" description="Generated lineups from the real nfl/solver.py optimizer.">
      <LineupsContent />
    </NflPageShell>
  );
}
