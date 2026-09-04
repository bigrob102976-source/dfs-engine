"use client";

import { MIN_UNIQUE_OPTIONS, STACK_TYPE_OPTIONS } from "@/lib/dkRosterRules";
import type { OptimizerPoolResult } from "@/lib/optimizerWorkspace/types";

interface ConstraintsPanelProps {
  pool: OptimizerPoolResult | null;
  locks: string[];
  exclusions: string[];
  maxExposure: Record<string, number>;
  onUnlock: (id: string) => void;
  onUnexclude: (id: string) => void;
  onClearExclusions: () => void;

  stackSize: number | null;
  stackTeam: string | null;
  // Multi-team stacks (M2): stackSize2/stackTeam2 are only ever
  // meaningful together (a "5-3" etc.) -- see STACK_TYPE_OPTIONS.
  stackSize2: number | null;
  stackTeam2: string | null;
  // Fires with BOTH sizes at once (a Stack Type preset click sets, e.g.,
  // 5+3 together -- there's no meaningful "pick just the primary size"
  // step for a two-team preset).
  onStackTypeChange: (stackSize: number | null, stackSize2: number | null) => void;
  onStackTeamChange: (team: string | null) => void;
  onStackTeam2Change: (team: string | null) => void;

  allowPitcherVsHitter: boolean;
  onAllowPitcherVsHitterChange: (value: boolean) => void;

  // PROBABLE FIX milestone: ON by default -- see dfs/eligibility.py's
  // PROBABLE_HITTER / lineup_confirmation for what "probable" means here.
  useProbableStarters: boolean;
  onUseProbableStartersChange: (value: boolean) => void;

  minSalary: number | null;
  onMinSalaryChange: (value: number | null) => void;

  minUnique: number;
  onMinUniqueChange: (value: number) => void;
}

export function ConstraintsPanel({
  pool,
  locks,
  exclusions,
  maxExposure,
  onUnlock,
  onUnexclude,
  onClearExclusions,
  stackSize,
  stackTeam,
  stackSize2,
  stackTeam2,
  onStackTypeChange,
  onStackTeamChange,
  onStackTeam2Change,
  allowPitcherVsHitter,
  onAllowPitcherVsHitterChange,
  useProbableStarters,
  onUseProbableStartersChange,
  minSalary,
  onMinSalaryChange,
  minUnique,
  onMinUniqueChange,
}: ConstraintsPanelProps) {
  const byId = new Map((pool?.players ?? []).map((p) => [p.dkPlayerId, p]));
  const teams = Array.from(new Set((pool?.players ?? []).map((p) => p.team))).sort();
  const salaryCap = pool?.salaryCap ?? 50000;

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded border border-border-subtle bg-bg-panel-raised p-3">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Locked ({locks.length})</div>
        {locks.length === 0 ? (
          <div className="text-[11px] text-text-faint">No players locked.</div>
        ) : (
          <ul className="flex flex-col gap-1">
            {locks.map((id) => {
              const player = byId.get(id);
              const exposurePercent = Math.round((maxExposure[id] ?? 1) * 100);
              return (
                <li key={id} className="flex items-center justify-between gap-2 text-xs">
                  <span className="truncate text-text">
                    {player?.name ?? id} <span className="text-text-faint">({player?.positions.join("/") ?? "?"})</span>
                  </span>
                  <span className="text-text-faint">{exposurePercent}%</span>
                  <button type="button" onClick={() => onUnlock(id)} className="text-[10px] text-accent hover:underline">
                    Remove
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="rounded border border-border-subtle bg-bg-panel-raised p-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">Excluded ({exclusions.length})</span>
          {exclusions.length > 0 && (
            <button type="button" onClick={onClearExclusions} className="text-[10px] text-accent hover:underline">
              Clear All
            </button>
          )}
        </div>
        {exclusions.length === 0 ? (
          <div className="text-[11px] text-text-faint">No players excluded.</div>
        ) : (
          <ul className="flex flex-col gap-1">
            {exclusions.map((id) => {
              const player = byId.get(id);
              return (
                <li key={id} className="flex items-center justify-between gap-2 text-xs">
                  <span className="truncate text-text">{player?.name ?? id}</span>
                  <button type="button" onClick={() => onUnexclude(id)} className="text-[10px] text-accent hover:underline">
                    Restore
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="rounded border border-border-subtle bg-bg-panel-raised p-3">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Stacking</div>
        <div className="mb-2 flex flex-wrap gap-1">
          {STACK_TYPE_OPTIONS.map((opt) => {
            const isSelected = stackSize === opt.stackSize && stackSize2 === opt.stackSize2;
            return (
              <button
                key={opt.label}
                type="button"
                onClick={() => onStackTypeChange(opt.stackSize, opt.stackSize2)}
                className={`rounded px-2 py-1 text-[11px] ${
                  isSelected ? "bg-accent-dim text-text" : "bg-bg-panel text-text-faint hover:text-text-muted"
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
        {(() => {
          const selectedType = STACK_TYPE_OPTIONS.find((opt) => opt.stackSize === stackSize && opt.stackSize2 === stackSize2);
          const requiresSecondaryTeam = selectedType?.requiresSecondaryTeam ?? false;
          return (
            <>
              <label className="mb-2 flex items-center gap-2 text-xs text-text-muted">
                Primary Team
                <select
                  value={stackTeam ?? ""}
                  onChange={(e) => onStackTeamChange(e.target.value || null)}
                  disabled={stackSize === null}
                  className="rounded border border-border bg-bg-panel px-2 py-1 text-text disabled:opacity-40"
                >
                  <option value="">{requiresSecondaryTeam ? "Select a team" : "Any"}</option>
                  {teams.map((team) => (
                    <option key={team} value={team}>
                      {team}
                    </option>
                  ))}
                </select>
              </label>
              {requiresSecondaryTeam && (
                <label className="mb-2 flex items-center gap-2 text-xs text-text-muted">
                  Secondary Team
                  <select
                    value={stackTeam2 ?? ""}
                    onChange={(e) => onStackTeam2Change(e.target.value || null)}
                    className="rounded border border-border bg-bg-panel px-2 py-1 text-text"
                  >
                    <option value="">Select a team</option>
                    {teams
                      .filter((team) => team !== stackTeam)
                      .map((team) => (
                        <option key={team} value={team}>
                          {team}
                        </option>
                      ))}
                  </select>
                </label>
              )}
              {requiresSecondaryTeam && !stackTeam && (
                <p className="mb-2 text-[10px] text-yellow">
                  Two-team stacks require an explicit Primary Team -- automatic team selection is not supported for two-team stacks.
                </p>
              )}
            </>
          );
        })()}
      </section>

      <section className="rounded border border-border-subtle bg-bg-panel-raised p-3">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Optimizer Settings</div>

        <label className="mb-2 flex items-center justify-between gap-2 text-xs text-text-muted">
          <span>Allow hitters vs opposing pitcher</span>
          <input
            type="checkbox"
            checked={allowPitcherVsHitter}
            onChange={(e) => onAllowPitcherVsHitterChange(e.target.checked)}
            className="accent-accent"
          />
        </label>
        <p className="mb-3 text-[10px] text-text-faint">
          When off, the optimizer will not roster hitters against one of your selected pitchers.
        </p>

        <label className="mb-2 flex items-center justify-between gap-2 text-xs text-text-muted">
          <span>Use Probable Starters</span>
          <input
            type="checkbox"
            checked={useProbableStarters}
            onChange={(e) => onUseProbableStartersChange(e.target.checked)}
            className="accent-accent"
          />
        </label>
        <p className="mb-3 text-[10px] text-text-faint">
          On by default. Includes real, evidence-based probable starters (see the Status column) before official lineups post. Confirmed
          starters are never affected by this setting.
          {!useProbableStarters && (
            <span className="mt-1 block text-yellow">
              Off, early in the day: with no official lineups posted yet, this can leave too few eligible hitters to build a legal lineup.
            </span>
          )}
        </p>

        <div className="mb-2 flex items-center justify-between text-xs text-text-muted">
          <span>Salary Cap</span>
          <span className="text-text">${salaryCap.toLocaleString()}</span>
        </div>
        <label className="mb-3 flex items-center justify-between gap-2 text-xs text-text-muted">
          Minimum Spend
          <input
            type="number"
            min={0}
            max={salaryCap}
            step={500}
            value={minSalary ?? ""}
            placeholder="none"
            onChange={(e) => {
              const raw = e.target.value;
              onMinSalaryChange(raw === "" ? null : Math.max(0, Math.min(salaryCap, Number(raw))));
            }}
            className="w-24 rounded border border-border bg-bg-panel px-2 py-1 text-right text-text outline-none focus:border-accent"
          />
        </label>

        <label className="flex items-center justify-between gap-2 text-xs text-text-muted">
          Minimum Unique Players
          <select
            value={minUnique}
            onChange={(e) => onMinUniqueChange(Number(e.target.value))}
            className="rounded border border-border bg-bg-panel px-2 py-1 text-text"
          >
            {MIN_UNIQUE_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      </section>
    </div>
  );
}
