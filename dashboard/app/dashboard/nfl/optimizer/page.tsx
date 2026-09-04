"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { DataCard, MetricCard, PrimaryButton, SecondaryButton } from "@/components/ui";
import { NflPageShell } from "@/components/nfl/NflPageShell";
import { NFL_ROSTER_SLOT_ORDER } from "@/lib/nfl/types";
import { loadLockExcludeState } from "@/lib/nfl/lockExcludeStorage";
import { saveOptimizeResult } from "@/lib/nfl/optimizeResultStorage";
import { useNflData } from "@/lib/nfl/useNflData";
import { useNflDraftGroupId } from "@/lib/nfl/useNflDraftGroupId";

function OptimizerContent() {
  const draftGroupId = useNflDraftGroupId();
  const { data, loading, error } = useNflData(draftGroupId);
  const router = useRouter();

  const [numLineups, setNumLineups] = useState(1);
  const [mode, setMode] = useState<"roster_feasibility" | "projection">("roster_feasibility");
  const [building, setBuilding] = useState(false);
  const [buildError, setBuildError] = useState<string | null>(null);

  if (loading && !data) return <p className="text-sm text-text-faint">Loading real NFL player pool…</p>;
  if (error) return <p className="text-sm text-red">{error}</p>;
  if (!data) return null;

  const lockExclude = loadLockExcludeState(draftGroupId);
  const projectedCount = data.players.filter((p) => p.projection?.projection !== null && p.projection?.projection !== undefined).length;
  const canBuildProjection = mode !== "projection" || projectedCount >= 9;

  async function build() {
    setBuilding(true);
    setBuildError(null);
    try {
      const res = await fetch("/api/nfl/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ draftGroupId, numLineups, mode, locks: lockExclude.locks, excludes: lockExclude.excludes }),
      });
      const json = await res.json();
      if (!res.ok || json.error) {
        setBuildError(json.error || "Build failed.");
        return;
      }
      saveOptimizeResult(draftGroupId, json);
      router.push(`/dashboard/nfl/lineups?draftGroupId=${draftGroupId}`);
    } catch (err) {
      setBuildError(err instanceof Error ? err.message : "Unknown error building lineups.");
    } finally {
      setBuilding(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard label="Roster" value="QB/RB/RB/WR/WR/WR/TE/FLEX/DST" />
        <MetricCard label="Salary Cap" value={`$${data.salary_cap.toLocaleString()}`} />
        <MetricCard label="Locked" value={lockExclude.locks.length} />
        <MetricCard label="Excluded" value={lockExclude.excludes.length} />
      </div>

      <DataCard title="Build Settings">
        <div className="flex flex-wrap items-end gap-4">
          <label className="text-xs text-text-muted">
            Mode
            <select value={mode} onChange={(e) => setMode(e.target.value as "roster_feasibility" | "projection")} className="mt-1 block rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-2 py-1.5 text-xs text-text">
              <option value="roster_feasibility">Roster Feasibility (legal lineup only)</option>
              <option value="projection">Projection (maximize Big Money Native)</option>
            </select>
          </label>
          <label className="text-xs text-text-muted">
            Lineup Count
            <input
              type="number"
              min={1}
              max={20}
              value={numLineups}
              onChange={(e) => setNumLineups(Math.max(1, Math.min(20, Number.parseInt(e.target.value, 10) || 1)))}
              className="mt-1 block w-20 rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-2 py-1.5 text-xs text-text"
            />
          </label>
          <PrimaryButton onClick={build} disabled={building || !canBuildProjection}>
            {building ? "Building…" : "Build Lineups"}
          </PrimaryButton>
          <SecondaryButton onClick={() => router.push(`/dashboard/nfl/players?draftGroupId=${draftGroupId}`)}>Edit Locks/Excludes</SecondaryButton>
        </div>
        {mode === "projection" && !canBuildProjection && (
          <p className="mt-2 text-xs text-yellow">
            Only {projectedCount} players currently have a real Big Money Native projection -- not enough real input to fill every roster slot in Projection mode.
          </p>
        )}
        {buildError && <p className="mt-2 text-xs text-red">{buildError}</p>}
        <p className="mt-3 text-[11px] text-text-faint">
          Big Money Native ownership (nfl_ownership_v1) is available for decision support -- see the Players/Projections tabs' Ownership column and each built lineup's
          per-player Ownership on the Lineups tab. Advanced stacking/correlation/leverage-aware objective controls are not built yet -- this workspace intentionally omits
          them rather than showing controls that do nothing.
        </p>
      </DataCard>

      <DataCard title="Roster Slots">
        <div className="flex flex-wrap gap-2 text-xs text-text-muted">
          {NFL_ROSTER_SLOT_ORDER.map((slot) => (
            <span key={slot} className="rounded-[var(--radius-control)] border border-border-subtle px-2 py-1">
              {slot}
            </span>
          ))}
        </div>
      </DataCard>
    </div>
  );
}

export default function NflOptimizerPage() {
  return (
    <NflPageShell title="NFL Optimizer" description="Real nfl/solver.py CP-SAT optimizer -- DK Classic roster, $50,000 cap.">
      <OptimizerContent />
    </NflPageShell>
  );
}
