"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { MissingDataState } from "@/components/MissingDataState";
import { PrimaryButton } from "@/components/ui/Button";
import { LINEUP_COUNT_OPTIONS, OPTIMIZER_OBJECTIVES } from "@/lib/dkRosterRules";
import { reconcileConstraintsWithPool } from "@/lib/optimizerWorkspace/reconcile";
import { resolveExternalSourceLabel } from "@/lib/projectionLabels";
import type { OptimizerBuildResult, OptimizerPoolResult, ProjectionSource, SlateOption } from "@/lib/optimizerWorkspace/types";
import { loadWorkspaceState, saveWorkspaceState } from "@/lib/optimizerWorkspace/workspaceStorage";

import { ConstraintsPanel } from "./ConstraintsPanel";
import { LineupsPanel } from "./LineupsPanel";
import { PoolTable } from "./PoolTable";

type Objective = "projection" | "ceiling" | "balanced" | "leverage";

const SLATE_STATUS_MESSAGES: Record<string, string> = {
  // Unset DFS_SALARY_PROVIDER now falls back to the mock provider automatically
  // (dfs/providers/config.py) -- this only fires when it's explicitly set to
  // something invalid, so the message points at fixing/clearing it, not "configure it".
  not_connected: "DFS_SALARY_PROVIDER is set to an unrecognized value. Fix it, or unset it to use the automatic mock fallback.",
  unavailable: "DFS provider unavailable.",
  auth_failed: "DFS provider authentication failed.",
  no_slate: "DFS provider returned no slate for today.",
};

function formatTime(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "--";
  return d.toLocaleString(undefined, { hour: "numeric", minute: "2-digit", timeZoneName: "short" });
}

/** The Milestone 14 interactive optimizer workspace: slate selection,
 * player-pool browsing/locking/excluding/exposure, stack/salary/unique
 * constraints, an authoritative live pre-solve validation panel, and a
 * BUILD action that runs the real CP-SAT optimizer server-side and
 * displays the resulting lineups + exposure summaries. Every server call
 * goes through /api/optimizer/* -- nothing here talks to Python
 * directly or invents projections/salaries/ownership. */
export function OptimizerWorkspace() {
  const searchParams = useSearchParams();
  const [hydrated, setHydrated] = useState(false);

  const [slates, setSlates] = useState<SlateOption[]>([]);
  const [slateStatus, setSlateStatus] = useState<string | null>(null);
  const [slateReason, setSlateReason] = useState<string | null>(null);
  const [providerIsMock, setProviderIsMock] = useState(false);
  const [slatesLoading, setSlatesLoading] = useState(true);

  const [selectedSlateId, setSelectedSlateId] = useState<string | null>(null);
  const [pool, setPool] = useState<OptimizerPoolResult | null>(null);
  const [poolLoading, setPoolLoading] = useState(false);
  const [poolError, setPoolError] = useState<string | null>(null);
  const [reconcileWarnings, setReconcileWarnings] = useState<string[]>([]);

  const [locks, setLocks] = useState<string[]>([]);
  const [exclusions, setExclusions] = useState<string[]>([]);
  const [maxExposure, setMaxExposure] = useState<Record<string, number>>({});
  const [stackSize, setStackSize] = useState<number | null>(null);
  const [stackTeam, setStackTeam] = useState<string | null>(null);
  const [allowPitcherVsHitter, setAllowPitcherVsHitter] = useState(false);
  const [minSalary, setMinSalary] = useState<number | null>(null);
  const [minUnique, setMinUnique] = useState(2);
  const [lineups, setLineups] = useState(20);
  const [objective, setObjective] = useState<Objective>("projection");
  // Milestone 23: defaults to Native Big Money DFS now that its
  // real-slate validation and no-external-dependency acceptance checks
  // have passed (see the milestone's final report) -- falls back to
  // Independent / Legacy automatically (effect further down) the moment
  // a slate has no native snapshot yet, so this is never a silent trap.
  const [projectionSource, setProjectionSource] = useState<ProjectionSource>("native");
  const [showProjectionComparison, setShowProjectionComparison] = useState(false);

  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [building, setBuilding] = useState(false);
  const [buildResult, setBuildResult] = useState<OptimizerBuildResult | null>(null);
  const [buildErrors, setBuildErrors] = useState<string[]>([]);

  // 1. Hydrate persisted UI preferences on mount (Milestone 14's "STATE
  // PERSISTENCE"). Deferred one microtask so every setState call happens
  // inside a callback rather than the effect's synchronous body --
  // satisfies react-hooks/set-state-in-effect while still running as
  // soon as possible after mount (localStorage is the "external system"
  // being synchronized from).
  useEffect(() => {
    Promise.resolve().then(() => {
      const persisted = loadWorkspaceState();
      if (persisted) {
        setSelectedSlateId(persisted.selectedSlateId);
        setLocks(persisted.locks);
        setExclusions(persisted.exclusions);
        setMaxExposure(persisted.maxExposure);
        setStackSize(persisted.stackSize);
        setStackTeam(persisted.stackTeam);
        setAllowPitcherVsHitter(persisted.allowPitcherVsHitter);
        setMinSalary(persisted.minSalary);
        setMinUnique(persisted.minUnique);
        setLineups(persisted.lineups);
        setObjective(persisted.objective);
        setProjectionSource(persisted.projectionSource ?? "native");
        setShowProjectionComparison(persisted.showProjectionComparison ?? false);
      }
      setHydrated(true);
    });
  }, []);

  // 1b. Milestone 26: the global slate selector (top nav) drives every
  // slate-aware page via a `?slate=` URL param -- if the Optimizer was
  // navigated to (or is already open) with that param set, it takes
  // priority over whatever slate was persisted from a previous session,
  // so switching the global dropdown always updates the Optimizer too.
  // Runs after hydration so it overrides rather than races the restore
  // above; a page load with no `?slate=` param leaves the persisted
  // selection untouched (direct navigation keeps working as before).
  useEffect(() => {
    if (!hydrated) return;
    const urlSlateId = searchParams?.get("slate");
    // Deferred one microtask, same rationale as the hydration effect
    // above: keeps the setState call out of the effect body itself.
    Promise.resolve().then(() => {
      if (urlSlateId && urlSlateId !== selectedSlateId) {
        setSelectedSlateId(urlSlateId);
      }
    });
    // Only ever reacts to the URL param changing (or hydration completing)
    // -- intentionally excludes selectedSlateId so a user manually picking
    // a different slate in the dropdown isn't immediately overridden back.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated, searchParams]);

  // 2. Persist on every relevant change, once hydrated (never before --
  // that would clobber a saved session with fresh-mount defaults).
  useEffect(() => {
    if (!hydrated) return;
    saveWorkspaceState({
      selectedSlateId,
      locks,
      exclusions,
      maxExposure,
      stackSize,
      stackTeam,
      allowPitcherVsHitter,
      minSalary,
      minUnique,
      lineups,
      objective,
      projectionSource,
      showProjectionComparison,
    });
  }, [
    hydrated, selectedSlateId, locks, exclusions, maxExposure, stackSize, stackTeam, allowPitcherVsHitter, minSalary, minUnique, lineups,
    objective, projectionSource, showProjectionComparison,
  ]);

  // 3. Discover today's slates once, right after hydration (so we know
  // whether a persisted selection still exists among them).
  useEffect(() => {
    if (!hydrated) return;
    Promise.resolve()
      .then(() => {
        setSlatesLoading(true);
        return fetch("/api/optimizer/slates");
      })
      .then((res) => res.json())
      .then((data) => {
        setSlateStatus(data.status ?? null);
        setSlateReason(data.reason ?? null);
        setProviderIsMock(Boolean(data.isMock));
        const list: SlateOption[] = data.slates ?? [];
        setSlates(list);
        setSlatesLoading(false);
        setSelectedSlateId((current) => {
          if (list.length === 1) return list[0].slateId;
          if (current && !list.some((s) => s.slateId === current)) return null;
          return current;
        });
      })
      .catch(() => {
        setSlatesLoading(false);
        setSlateStatus("unavailable");
      });
    // Runs once, right after hydration -- deliberately not re-run on every
    // selectedSlateId change (that's handled by the selectedSlateId effect below).
  }, [hydrated]);

  // 4. Load the selected slate's player pool. Reconciles existing
  // locks/exclusions/exposures/stackTeam against the new pool (Milestone
  // 14's "SLATE CHANGE" / "REFRESH BEHAVIOR" requirements). Pulled out of
  // the effect below so Milestone 16's "Prepare Optimizer Data" action can
  // also call it directly, once its background orchestrator run finishes,
  // to reload the pool without a manual browser refresh.
  const loadPool = useCallback((slateId: string) => {
    Promise.resolve()
      .then(() => {
        setPoolLoading(true);
        setPoolError(null);
        setBuildResult(null);
        setBuildErrors([]);
        return fetch("/api/optimizer/pool", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ slateId }),
        });
      })
      .then((res) => res.json())
      .then((data) => {
        setPoolLoading(false);
        if (data.error) {
          setPoolError(data.error);
          setPool(null);
          return;
        }
        const newPool: OptimizerPoolResult = data.pool;

        // Milestone 26 live validation (real DK Main/Turbo CSVs, 2026-08-12)
        // uncovered a real ID-collision hazard: DraftKings' numeric `ID`
        // column is only unique WITHIN a single slate export, not across
        // different slates sharing a date -- e.g. id 1006 was Merrill
        // Kelly in that day's Main export but Trevor Larnach in Turbo's.
        // Reconciling locks/exclusions/exposures by raw dkPlayerId across
        // an actual slate CHANGE can therefore silently re-target a lock
        // at a completely different person. Reconciling by id is still
        // correct (and desired, to drop scratches) for a same-slate pool
        // refresh, since id collisions can't happen within one slate's own
        // export -- so only a genuine slate switch resets instead.
        const isSlateSwitch = pool !== null && pool.slateId !== newPool.slateId;
        setPool(newPool);

        const reconciled = isSlateSwitch
          ? {
              state: { locks: [], exclusions: [], maxExposure: {} },
              warnings: [
                `Switched slates (${pool!.slateName ?? pool!.slateId} → ${newPool.slateName ?? newPool.slateId}) -- locks, exclusions, and exposure targets were reset. DraftKings player IDs are only unique within one slate export, so constraints can't be safely carried across different slates.`,
              ],
            }
          : reconcileConstraintsWithPool(newPool, { locks, exclusions, maxExposure });
        setLocks(reconciled.state.locks);
        setExclusions(reconciled.state.exclusions);
        setMaxExposure(reconciled.state.maxExposure);
        setReconcileWarnings(reconciled.warnings);

        const teams = new Set(newPool.players.map((p) => p.team));
        setStackTeam((prevTeam) => (prevTeam && !teams.has(prevTeam) ? null : prevTeam));
      })
      .catch(() => {
        setPoolLoading(false);
        setPoolError("Failed to load player pool.");
      });
  }, [locks, exclusions, maxExposure, pool]);

  useEffect(() => {
    if (!hydrated || !selectedSlateId) return;
    loadPool(selectedSlateId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated, selectedSlateId]);

  const buildRequestBody = useCallback(() => {
    const byId = new Map((pool?.players ?? []).map((p) => [p.dkPlayerId, p]));
    const lockNames = locks.map((id) => byId.get(id)?.name).filter((n): n is string => Boolean(n));
    const exclusionNames = exclusions.map((id) => byId.get(id)?.name).filter((n): n is string => Boolean(n));
    const maxExposureByName: Record<string, number> = {};
    for (const [id, fraction] of Object.entries(maxExposure)) {
      const name = byId.get(id)?.name;
      if (name) maxExposureByName[name] = fraction;
    }
    return {
      slateId: selectedSlateId,
      lineups,
      objective,
      locks: lockNames,
      exclusions: exclusionNames,
      maxExposure: maxExposureByName,
      stackSize,
      stackTeam,
      allowPitcherVsHitter,
      minSalary,
      minUnique,
      projectionSource,
    };
  }, [
    pool, locks, exclusions, maxExposure, selectedSlateId, lineups, objective, stackSize, stackTeam, allowPitcherVsHitter, minSalary, minUnique,
    projectionSource,
  ]);

  // Milestone 17/20/23: if the newly-selected slate has no data for the
  // currently-selected projection source, fall back to Independent /
  // Legacy rather than silently building against a source that doesn't
  // exist for it.
  useEffect(() => {
    if (!pool) return;
    const externalUnavailable = (projectionSource === "external" || projectionSource === "adjusted") && !pool.hasExternalProjections;
    const aiUnavailable = projectionSource === "ai" && !pool.hasAiProjections;
    const nativeUnavailable = projectionSource === "native" && !pool.hasNativeProjections;
    if (externalUnavailable || aiUnavailable || nativeUnavailable) {
      Promise.resolve().then(() => setProjectionSource("independent"));
    }
  }, [pool, projectionSource]);

  // 5. Debounced, authoritative pre-solve validation (reuses the real
  // optimizer's own resolve_settings()/pre_solve_diagnostics() via
  // /api/optimizer/validate -- never the CP-SAT solver).
  useEffect(() => {
    if (!pool) {
      Promise.resolve().then(() => setValidationErrors([]));
      return;
    }
    const handle = setTimeout(() => {
      fetch("/api/optimizer/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildRequestBody()),
      })
        .then((res) => res.json())
        .then((data) => setValidationErrors(data.errors ?? []))
        .catch(() => setValidationErrors([]));
    }, 500);
    return () => clearTimeout(handle);
  }, [pool, locks, exclusions, maxExposure, stackSize, stackTeam, allowPitcherVsHitter, minSalary, minUnique, objective, buildRequestBody]);

  function handleBuild() {
    setBuilding(true);
    setBuildErrors([]);
    fetch("/api/optimizer/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildRequestBody()),
    })
      .then((res) => res.json())
      .then((data) => {
        setBuilding(false);
        const result: OptimizerBuildResult | undefined = data.result;
        if (!result || !result.ok) {
          setBuildErrors(result?.errors ?? [data.error ?? "Build failed."]);
          setBuildResult(null);
        } else {
          setBuildResult(result);
        }
      })
      .catch(() => {
        setBuilding(false);
        setBuildErrors(["Build request failed."]);
      });
  }

  function toggleLock(id: string) {
    setLocks((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
    setExclusions((prev) => prev.filter((x) => x !== id));
  }
  function toggleExclude(id: string) {
    setExclusions((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
    setLocks((prev) => prev.filter((x) => x !== id));
  }
  function setExposure(id: string, fraction: number) {
    setMaxExposure((prev) => {
      if (fraction >= 1) {
        const rest = { ...prev };
        delete rest[id];
        return rest;
      }
      return { ...prev, [id]: fraction };
    });
  }

  const selectedSlate = slates.find((s) => s.slateId === selectedSlateId) ?? null;
  const externalSourceLabel = resolveExternalSourceLabel(pool?.externalProviderName ?? null);

  return (
    <div className="flex flex-col gap-4">
      {/* TOP CONTROL BAR */}
      <div className="flex flex-wrap items-center gap-3 rounded-[var(--radius-card)] border border-border bg-bg-panel p-3 shadow-[var(--shadow-card)]">
        <div className="flex items-center gap-1">
          <span className="rounded bg-accent-dim px-2 py-1 text-xs font-semibold text-text">DraftKings</span>
          <span className="cursor-not-allowed rounded bg-bg-panel-raised px-2 py-1 text-xs text-text-faint" title="FanDuel support is not implemented in this milestone">
            FanDuel -- Coming Soon
          </span>
        </div>

        <label className="flex items-center gap-2 text-xs text-text-muted">
          Slate:
          <select
            value={selectedSlateId ?? ""}
            onChange={(e) => setSelectedSlateId(e.target.value || null)}
            disabled={slatesLoading || slates.length === 0}
            className="min-w-[220px] rounded border border-border bg-bg-panel-raised px-2 py-1 text-text disabled:opacity-40"
          >
            <option value="">{slatesLoading ? "Loading slates..." : slates.length === 0 ? "No slates available" : "Select a slate"}</option>
            {slates.map((s) => (
              <option key={s.slateId} value={s.slateId}>
                {s.slateName ?? s.slateId}
                {s.startTime ? ` -- ${s.startTime}` : ""}
                {s.gameCount != null ? ` -- ${s.gameCount} games` : ""}
              </option>
            ))}
          </select>
        </label>

        {providerIsMock && <span className="rounded bg-yellow/20 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-yellow">DEV / MOCK DATA</span>}

        {pool && pool.vegasCoverage.dkGames > 0 && (
          <span
            className={`rounded px-2 py-1 text-[10px] font-semibold uppercase tracking-wide ${
              pool.vegasCoverage.pregameCovered === pool.vegasCoverage.dkGames ? "bg-green/15 text-green" : "bg-yellow/20 text-yellow"
            }`}
            title="Native/AI projections still run with missing Vegas -- a missing game's Vegas adjustment is simply 0."
          >
            Vegas {pool.vegasCoverage.pregameCovered}/{pool.vegasCoverage.dkGames} Pregame Covered
          </span>
        )}

        <span className="text-[11px] text-text-faint">Updated: {pool ? formatTime(pool.generatedAt) : "--"}</span>

        <div className="ml-auto flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-text-muted">
            Lineups
            <select value={lineups} onChange={(e) => setLineups(Number(e.target.value))} className="rounded border border-border bg-bg-panel-raised px-2 py-1 text-text">
              {LINEUP_COUNT_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-2 text-xs text-text-muted" title={OPTIMIZER_OBJECTIVES.find((o) => o.value === objective)?.explanation}>
            Objective
            <select value={objective} onChange={(e) => setObjective(e.target.value as Objective)} className="rounded border border-border bg-bg-panel-raised px-2 py-1 text-text">
              {OPTIMIZER_OBJECTIVES.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>

          <PrimaryButton onClick={handleBuild} disabled={!pool || building || validationErrors.length > 0} className="uppercase tracking-wide">
            {building ? "Solving..." : "Build Lineups"}
          </PrimaryButton>
        </div>
      </div>

      {/* Milestone 17/23/27: PROJECTION SOURCE SELECTOR. Native and AI
          (Big Money's own model-driven sources) lead, BlueCollar/BlueCollar
          (Adjusted) follow, Legacy (the original Milestone 2-era scoring
          baseline) is last. Milestone 27: every label is now unambiguous
          (see lib/projectionLabels.ts) -- "external"/"adjusted" no longer
          show a bare "External," they show "BlueCollar" when the loaded
          baseline really is BlueCollar, or the honest "External Other"
          when it's some other (e.g. mock) provider -- never presenting
          one provider's data as if it were another's. */}
      <div className="flex flex-wrap items-center gap-3 rounded-[var(--radius-card)] border border-border bg-bg-panel p-3 shadow-[var(--shadow-card)]">
        <span className="text-xs font-medium uppercase tracking-wide text-text-muted">Projection Source</span>
        <div className="flex gap-1" role="group" aria-label="Projection Source">
          {(
            [
              { value: "native" as ProjectionSource, label: "Big Money Native" },
              { value: "ai" as ProjectionSource, label: "Big Money AI" },
              { value: "external" as ProjectionSource, label: externalSourceLabel },
              { value: "adjusted" as ProjectionSource, label: `${externalSourceLabel} (Adjusted)` },
              { value: "independent" as ProjectionSource, label: "Legacy" },
            ]
          ).map((opt) => {
            const disabled =
              opt.value === "ai" ? !pool?.hasAiProjections
              : opt.value === "native" ? !pool?.hasNativeProjections
              : opt.value !== "independent" && !pool?.hasExternalProjections;
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => setProjectionSource(opt.value)}
                disabled={disabled}
                aria-pressed={projectionSource === opt.value}
                className={`rounded px-2 py-1 text-xs font-medium ${
                  projectionSource === opt.value
                    ? opt.value === "ai" || opt.value === "native"
                      ? "bg-purple/20 text-purple"
                      : "bg-accent-dim text-text"
                    : "bg-bg-panel-raised text-text-faint hover:text-text-muted"
                } disabled:cursor-not-allowed disabled:opacity-40`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
        {!pool?.hasExternalProjections && <span className="text-[11px] text-text-faint">{externalSourceLabel} not loaded -- import via Results / Projection Import Center.</span>}
        {!pool?.hasAiProjections && (
          <span className="text-[11px] text-text-faint">Big Money AI not generated yet -- run scripts/run_ai_projection_engine.py.</span>
        )}
        {!pool?.hasNativeProjections && (
          <span className="text-[11px] text-text-faint">Big Money Native not generated yet -- run scripts/run_native_projection_engine.py.</span>
        )}

        <label className="ml-auto flex items-center gap-1.5 text-xs text-text-muted">
          <input type="checkbox" checked={showProjectionComparison} onChange={(e) => setShowProjectionComparison(e.target.checked)} />
          Show comparison columns
        </label>
      </div>

      {slateStatus && slateStatus !== "ready" && (
        <div className="rounded border border-red bg-bg-panel-raised px-3 py-2 text-xs text-red">
          {SLATE_STATUS_MESSAGES[slateStatus] ?? slateReason ?? `Slate status: ${slateStatus}`}
        </div>
      )}
      {poolError && <div className="rounded border border-red bg-bg-panel-raised px-3 py-2 text-xs text-red">{poolError}</div>}
      {reconcileWarnings.length > 0 && (
        <div className="rounded border border-yellow bg-bg-panel-raised px-3 py-2 text-xs text-yellow">{reconcileWarnings.join(" ")}</div>
      )}

      {pool && (
        <div className="grid grid-cols-2 gap-3 rounded-[var(--radius-card)] border border-border bg-bg-panel p-3 text-xs shadow-[var(--shadow-card)] md:grid-cols-4 lg:grid-cols-7">
          <StatusStat label="Active Players" value={pool.activePlayers} />
          <StatusStat label="Pitchers" value={pool.pitcherCount} />
          <StatusStat label="Hitters" value={pool.hitterCount} />
          <StatusStat label="Confirmed Lineups" value={pool.confirmedLineupGames} />
          <StatusStat label="Unconfirmed Lineups" value={pool.unconfirmedLineupGames} />
          <StatusStat label="Unmatched" value={pool.unmatchedCount} />
          <StatusStat label="Slate Games" value={pool.slateGames} />
        </div>
      )}

      {validationErrors.length > 0 && (
        <div className="rounded border border-red bg-bg-panel-raised p-3 text-xs">
          <div className="mb-1 font-semibold uppercase tracking-wide text-red">Unable to build:</div>
          <ul className="list-inside list-disc text-text-muted">
            {validationErrors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}
      {buildErrors.length > 0 && (
        <div className="rounded border border-red bg-bg-panel-raised p-3 text-xs">
          <div className="mb-1 font-semibold uppercase tracking-wide text-red">Build failed:</div>
          <ul className="list-inside list-disc text-text-muted">
            {buildErrors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      {/* THREE-ZONE LAYOUT: stacked on narrow screens, side-by-side at lg+ */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[280px_1fr_360px]">
        <div className="min-w-0">
          <ConstraintsPanel
            pool={pool}
            locks={locks}
            exclusions={exclusions}
            maxExposure={maxExposure}
            onUnlock={toggleLock}
            onUnexclude={toggleExclude}
            onClearExclusions={() => setExclusions([])}
            stackSize={stackSize}
            stackTeam={stackTeam}
            onStackSizeChange={setStackSize}
            onStackTeamChange={setStackTeam}
            allowPitcherVsHitter={allowPitcherVsHitter}
            onAllowPitcherVsHitterChange={setAllowPitcherVsHitter}
            minSalary={minSalary}
            onMinSalaryChange={setMinSalary}
            minUnique={minUnique}
            onMinUniqueChange={setMinUnique}
          />
        </div>

        <div className="min-w-0">
          {pool && pool.activePlayers === 0 ? (
            <MissingDataState
              title="Optimizer data is not ready for this slate"
              description="The player pool has no active players yet -- pitcher and hitter research needs to be generated first."
              primaryActionLabel="Prepare Optimizer Data"
              targetSteps={["pitchers", "batters"]}
              onReady={() => selectedSlateId && loadPool(selectedSlateId)}
            />
          ) : pool ? (
            <PoolTable
              players={pool.players}
              locks={new Set(locks)}
              exclusions={new Set(exclusions)}
              maxExposure={maxExposure}
              onToggleLock={toggleLock}
              onToggleExclude={toggleExclude}
              onExposureChange={setExposure}
              showProjectionComparison={showProjectionComparison}
            />
          ) : (
            <div className="rounded border border-border bg-bg-panel p-6 text-center text-sm text-text-faint">
              {poolLoading ? "Loading player pool..." : selectedSlate ? "No player data yet." : "Select a slate to load its player pool."}
            </div>
          )}
        </div>

        <div className="min-w-0">
          {buildResult ? (
            <LineupsPanel result={buildResult} />
          ) : (
            <div className="rounded border border-border bg-bg-panel p-6 text-center text-sm text-text-faint">
              Configure locks, exclusions, and stacking, then click Build Lineups.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusStat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-text-faint">{label}</div>
      <div className="text-sm font-semibold text-text">{value}</div>
    </div>
  );
}
