"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { DataCard, MetricCard, PrimaryButton, SecondaryButton } from "@/components/ui";
import { NflPageShell } from "@/components/nfl/NflPageShell";
import { NflExposureEditor } from "@/components/nfl/NflExposureEditor";
import { DEFAULT_NFL_STACK_CONFIG, NFL_ROSTER_SLOT_ORDER, type NflObjectiveMode, type NflStackConfig } from "@/lib/nfl/types";
import { loadExposureState } from "@/lib/nfl/exposureStorage";
import { loadLockExcludeState } from "@/lib/nfl/lockExcludeStorage";
import { saveOptimizeResult } from "@/lib/nfl/optimizeResultStorage";
import { useNflData } from "@/lib/nfl/useNflData";
import { useNflDraftGroupId } from "@/lib/nfl/useNflDraftGroupId";

const OBJECTIVE_EXPLANATIONS: Record<NflObjectiveMode, string> = {
  roster_feasibility: "Builds a legal, salary-valid lineup only -- not a fantasy-points recommendation.",
  projection: "Maximizes total Big Money Native projected points.",
  ceiling: "Maximizes total Big Money Native ceiling (upside) instead of the median projection.",
  leverage: "Maximizes projection/ceiling, with a small bonus for players who look better than their real ownership suggests.",
};

function OptimizerContent() {
  const draftGroupId = useNflDraftGroupId();
  const { data, loading, error } = useNflData(draftGroupId);
  const router = useRouter();

  const [numLineups, setNumLineups] = useState(1);
  const [mode, setMode] = useState<NflObjectiveMode>("roster_feasibility");
  const [stack, setStack] = useState<NflStackConfig>(DEFAULT_NFL_STACK_CONFIG);
  const [maxExposureDefaultPct, setMaxExposureDefaultPct] = useState(100);
  const [building, setBuilding] = useState(false);
  const [buildError, setBuildError] = useState<string | null>(null);

  if (loading && !data) return <p className="text-sm text-text-faint">Loading real NFL player pool…</p>;
  if (error) return <p className="text-sm text-red">{error}</p>;
  if (!data) return null;

  const lockExclude = loadLockExcludeState(draftGroupId);
  const isScoringMode = mode !== "roster_feasibility";
  const dataReadyCount = data.players.filter((p) =>
    mode === "ceiling" || mode === "leverage"
      ? p.projection?.projection !== null && p.projection?.projection !== undefined && p.projection?.ceiling !== null && p.projection?.ceiling !== undefined
      : p.projection?.projection !== null && p.projection?.projection !== undefined,
  ).length;
  const canBuild = !isScoringMode || dataReadyCount >= 9;

  async function build() {
    setBuilding(true);
    setBuildError(null);
    try {
      const exposure = loadExposureState(draftGroupId);
      const res = await fetch("/api/nfl/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          draftGroupId, numLineups, mode, locks: lockExclude.locks, excludes: lockExclude.excludes,
          stack, maxExposure: exposure.maxExposure, maxExposureDefault: maxExposureDefaultPct / 100, minExposure: exposure.minExposure,
        }),
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
            Objective
            <select value={mode} onChange={(e) => setMode(e.target.value as NflObjectiveMode)} className="mt-1 block rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-2 py-1.5 text-xs text-text">
              <option value="roster_feasibility">Roster Feasibility (legal lineup only)</option>
              <option value="projection">Projection</option>
              <option value="ceiling">Ceiling</option>
              <option value="leverage">Leverage</option>
            </select>
          </label>
          <label className="text-xs text-text-muted">
            Lineup Count
            <input
              type="number"
              min={1}
              max={50}
              value={numLineups}
              onChange={(e) => setNumLineups(Math.max(1, Math.min(50, Number.parseInt(e.target.value, 10) || 1)))}
              className="mt-1 block w-20 rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-2 py-1.5 text-xs text-text"
            />
          </label>
          <PrimaryButton onClick={build} disabled={building || !canBuild}>
            {building ? "Building…" : "Build Lineups"}
          </PrimaryButton>
          <SecondaryButton onClick={() => router.push(`/dashboard/nfl/players?draftGroupId=${draftGroupId}`)}>Edit Locks/Excludes</SecondaryButton>
        </div>
        <p className="mt-2 text-[11px] text-text-faint">{OBJECTIVE_EXPLANATIONS[mode]}</p>
        {isScoringMode && !canBuild && (
          <p className="mt-2 text-xs text-yellow">
            Only {dataReadyCount} players currently have the real Big Money Native data this objective needs -- not enough to fill every roster slot.
          </p>
        )}
        {buildError && <p className="mt-2 text-xs text-red">{buildError}</p>}
      </DataCard>

      <DataCard title="Stacking">
        <div className="flex flex-wrap items-end gap-4">
          <label className="text-xs text-text-muted">
            QB Stack
            <select
              value={stack.qbStackMode}
              onChange={(e) => {
                const qbStackMode = e.target.value as typeof stack.qbStackMode;
                setStack((s) => ({ ...s, qbStackMode, bringBackMode: qbStackMode === "off" ? "off" : s.bringBackMode }));
              }}
              className="mt-1 block rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-2 py-1.5 text-xs text-text"
            >
              <option value="off">OFF</option>
              <option value="single">Single (QB + 1 WR/TE)</option>
              <option value="double">Double (QB + 2 WR/TE)</option>
            </select>
          </label>
          <label className="text-xs text-text-muted">
            Bring Back
            <select
              value={stack.bringBackMode}
              disabled={stack.qbStackMode === "off"}
              onChange={(e) => setStack((s) => ({ ...s, bringBackMode: e.target.value as typeof stack.bringBackMode }))}
              className="mt-1 block rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-2 py-1.5 text-xs text-text disabled:opacity-40"
            >
              <option value="off">OFF</option>
              <option value="one">1 opposing RB/WR/TE</option>
            </select>
          </label>
          <label className="flex items-center gap-1.5 text-xs text-text-muted">
            <input
              type="checkbox"
              checked={stack.rbDstEnabled}
              onChange={(e) => setStack((s) => ({ ...s, rbDstEnabled: e.target.checked }))}
              className="h-3.5 w-3.5"
            />
            RB + DST
          </label>
          <label className="text-xs text-text-muted">
            Max Players / Team
            <input
              type="number" min={1} max={9} placeholder="unlimited"
              value={stack.maxPlayersPerTeam ?? ""}
              onChange={(e) => setStack((s) => ({ ...s, maxPlayersPerTeam: e.target.value === "" ? null : Number(e.target.value) }))}
              className="mt-1 block w-24 rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-2 py-1.5 text-xs text-text"
            />
          </label>
          <label className="text-xs text-text-muted">
            Max Players / Game
            <input
              type="number" min={1} max={9} placeholder="unlimited"
              value={stack.maxPlayersPerGame ?? ""}
              onChange={(e) => setStack((s) => ({ ...s, maxPlayersPerGame: e.target.value === "" ? null : Number(e.target.value) }))}
              className="mt-1 block w-24 rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-2 py-1.5 text-xs text-text"
            />
          </label>
        </div>
        <p className="mt-2 text-[11px] text-text-faint">
          Bring Back requires QB Stack to be Single or Double -- it brings back an opposing (never DST) RB/WR/TE against your stacked QB&apos;s team.
        </p>
      </DataCard>

      <DataCard title="Exposure">
        <label className="text-xs text-text-muted">
          Default Max Exposure %
          <input
            type="number" min={0} max={100}
            value={maxExposureDefaultPct}
            onChange={(e) => setMaxExposureDefaultPct(Math.max(0, Math.min(100, Number.parseInt(e.target.value, 10) || 0)))}
            className="mt-1 ml-2 inline-block w-20 rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-2 py-1.5 text-xs text-text"
          />
        </label>
        <p className="mt-1 mb-3 text-[11px] text-text-faint">
          Applies to every player without an override below. A locked player is always 100% exposure.
        </p>
        <NflExposureEditor players={data.players} draftGroupId={draftGroupId} />
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
