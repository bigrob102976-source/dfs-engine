"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { DataCard, PrimaryButton, SecondaryButton } from "@/components/ui";
import { NflPageShell } from "@/components/nfl/NflPageShell";
import { fmt, fmtOwnership, fmtSalary } from "@/lib/nfl/format";
import type { NflLateSwapResult, NflSavedLineup } from "@/lib/nfl/types";
import { NFL_ROSTER_SLOT_ORDER } from "@/lib/nfl/types";
import { useNflDraftGroupId } from "@/lib/nfl/useNflDraftGroupId";

function LateSwapContent() {
  const params = useParams<{ id: string }>();
  const draftGroupId = useNflDraftGroupId();
  const router = useRouter();

  const [saved, setSaved] = useState<NflSavedLineup | null>(null);
  const [preview, setPreview] = useState<NflLateSwapResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [applied, setApplied] = useState(false);

  async function loadPreview() {
    setBusy(true);
    setError(null);
    try {
      const lineupRes = await fetch(`/api/nfl/lineups/${params.id}`);
      const lineupJson = await lineupRes.json();
      if (!lineupRes.ok) {
        setError(lineupJson.error || "Saved lineup not found.");
        return;
      }
      setSaved(lineupJson);

      const swapRes = await fetch(`/api/nfl/lineups/${params.id}/late-swap`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: lineupJson.mode, apply: false }),
      });
      const swapJson = await swapRes.json();
      if (!swapRes.ok) {
        setError(swapJson.error || "Late swap preview failed.");
        return;
      }
      setPreview(swapJson);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error running late swap.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    loadPreview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  async function applySwap() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/nfl/lineups/${params.id}/late-swap`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: saved?.mode, apply: true }),
      });
      const json = await res.json();
      if (!res.ok || json.error) {
        setError(json.error || "Late swap failed to apply.");
        return;
      }
      setApplied(true);
      await loadPreview();
    } finally {
      setBusy(false);
    }
  }

  if (error) return <p className="text-sm text-red">{error}</p>;
  if (!saved || !preview) return <p className="text-sm text-text-faint">Loading real game lock state…</p>;

  const lineup = preview.lineup;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <SecondaryButton onClick={() => router.push(`/dashboard/nfl/saved?draftGroupId=${draftGroupId}`)} className="px-2 py-1 text-xs">
          ← Back to Saved Lineups
        </SecondaryButton>
        <PrimaryButton onClick={applySwap} disabled={busy || preview.fully_locked} className="px-3 py-1.5 text-xs">
          {busy ? "Working…" : "Optimize Remaining Players"}
        </PrimaryButton>
        {applied && <span className="text-xs text-accent">Saved.</span>}
      </div>

      {preview.fully_locked && (
        <p className="rounded-[var(--radius-control)] border border-yellow/40 bg-yellow/10 p-2 text-xs text-yellow">
          Every player&apos;s real game has already started -- this lineup is fully locked. Late swap made no changes.
        </p>
      )}

      <DataCard title="Lock State">
        <div className="flex flex-wrap gap-4 text-xs text-text-muted">
          <span>
            Locked slots: <span className="font-semibold text-text">{preview.locked_slots.join(", ") || "none"}</span>
          </span>
          <span>
            Unlocked slots: <span className="font-semibold text-text">{preview.unlocked_slots.join(", ") || "none"}</span>
          </span>
          {preview.changed_player_keys.length > 0 && (
            <span>
              Players changed: <span className="font-semibold text-text">{preview.changed_player_keys.length}</span>
            </span>
          )}
        </div>
      </DataCard>

      {lineup && (
        <DataCard title="Lineup (preview)">
          <div className="mb-2 flex flex-wrap gap-4 text-xs text-text-muted">
            <span>
              Total Salary: <span className="font-semibold text-text">{fmtSalary(lineup.total_salary)}</span>
            </span>
            {lineup.total_projection !== null && (
              <span>
                Total Projection: <span className="font-semibold text-text">{fmt(lineup.total_projection)}</span>
              </span>
            )}
          </div>
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-border-subtle text-text-faint">
                <th className="py-1.5 pr-3 font-medium">Slot</th>
                <th className="py-1.5 pr-3 font-medium">Player</th>
                <th className="py-1.5 pr-3 font-medium">Team</th>
                <th className="py-1.5 pr-3 font-medium">Salary</th>
                <th className="py-1.5 pr-3 font-medium">Ownership</th>
                <th className="py-1.5 pr-3 font-medium">Status</th>
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
                    <td className="py-1.5 pr-3 text-[10px] uppercase text-text-faint">
                      {a?.locked ? <span className="text-red">Locked</span> : <span className="text-accent">Swappable</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </DataCard>
      )}

      <p className="text-[11px] text-text-faint">
        Locked players (their real DraftKings game has already started) can never be removed, excluded, or replaced -- only unlocked slots are
        re-optimized against current projections, ownership, and status. &quot;Optimize Remaining Players&quot; saves the result back onto this
        lineup; reload this page any time to re-check lock state as more real games start.
      </p>
    </div>
  );
}

export default function NflLateSwapPage() {
  return (
    <NflPageShell title="NFL Late Swap" description="Real per-game lock state -- locked players are never altered.">
      <LateSwapContent />
    </NflPageShell>
  );
}
