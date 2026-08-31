"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { MissingDataState } from "@/components/MissingDataState";
import { PrimaryButton } from "@/components/ui/Button";
import { LINEUP_COUNT_OPTIONS, OPTIMIZER_OBJECTIVES } from "@/lib/dkRosterRules";
import { reconcileConstraintsWithPool } from "@/lib/optimizerWorkspace/reconcile";
import { resolveExternalSourceLabel } from "@/lib/projectionLabels";
import type { BigMoneyMlCoverage } from "@/lib/bigMoneyMlOptimizer";
import type { OptimizerBuildResult, OptimizerCoverageSummary, OptimizerPoolResult, ProjectionSource, SlateOption } from "@/lib/optimizerWorkspace/types";
import { loadWorkspaceState, saveWorkspaceState } from "@/lib/optimizerWorkspace/workspaceStorage";
import { isValidSlateDateString } from "@/lib/slateDate";

import { ConstraintsPanel } from "./ConstraintsPanel";
import { LineupsPanel } from "./LineupsPanel";
import { PoolTable } from "./PoolTable";

type Objective = "projection" | "ceiling" | "balanced" | "leverage";

const SLATE_STATUS_MESSAGES: Record<string, string> = {
  // Milestone M1: "not_connected" now fires either for an explicit-but-
  // invalid DFS_SALARY_PROVIDER override, OR for DraftKings Unofficial
  // (the permanent default provider) itself being unavailable/disabled
  // -- two different real causes, so no single static message here would
  // be accurate. Falls through to the real `slateReason` from Python
  // (dfs/providers/config.py) wherever this map has no entry for the
  // current status -- see the render call below.
  unavailable: "DFS provider unavailable.",
  auth_failed: "DFS provider authentication failed.",
  no_slate: "DFS provider returned no slate for today.",
};

// Milestone 32.6 Part 3: short, honest per-source explanation shown
// under the Projection Source selector once a source is picked -- copy
// as specified by the milestone, verbatim.
const PROJECTION_SOURCE_EXPLANATIONS: Partial<Record<ProjectionSource, string>> = {
  big_money_ml: "History-trained models / Experimental / Owner Test",
  native: "Deterministic Big Money projection engine",
  ai: "Context-adjusted Big Money projection",
  fantasypros: "External comparison source",
  bluecollar: "Live BlueCollar DFS projections -- external comparison source",
};

function formatTime(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "--";
  return d.toLocaleString(undefined, { hour: "numeric", minute: "2-digit", timeZoneName: "short" });
}

// Worker-reliability fix: "DraftKings data last updated N minutes ago"
// wording for the stale-data notice -- minutes below an hour, then
// "1h 12m" style beyond that.
function formatAgeMinutes(ageSeconds: number): string {
  const minutes = Math.round(ageSeconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"}`;
  const hours = Math.floor(minutes / 60);
  const remMinutes = minutes % 60;
  return `${hours}h${remMinutes ? ` ${remMinutes}m` : ""}`;
}

/** The Milestone 14 interactive optimizer workspace: slate selection,
 * player-pool browsing/locking/excluding/exposure, stack/salary/unique
 * constraints, an authoritative live pre-solve validation panel, and a
 * BUILD action that runs the real CP-SAT optimizer server-side and
 * displays the resulting lineups + exposure summaries. Every server call
 * goes through /api/optimizer/* -- nothing here talks to Python
 * directly or invents projections/salaries/ownership.
 *
 * Milestone 31.2C: `initialDate` (from the page's own `?date=` -- see
 * app/dashboard/optimizer/page.tsx) seeds which calendar date's slates
 * to browse, since DraftKings' live lobby can roll to the next day
 * before Chicago midnight (lib/slateDate.ts). `null` means "no explicit
 * date" -- selectedDate then falls back to whatever was persisted from
 * a previous session, or stays null (server APIs default to Chicago-
 * today themselves, exactly matching this component's pre-M31.2C
 * behavior when selectedDate is never set at all).
 *
 * Milestone 32.4: `canUseBigMoneyMl` is resolved SERVER-SIDE (see
 * app/dashboard/optimizer/page.tsx) from the 'mlb.big_money_ml_optimizer'
 * feature flag (default ADMIN_ONLY) -- this prop only controls whether
 * the option is OFFERED in this component's UI; actual authorization is
 * enforced again server-side in /api/optimizer/build and /validate, so
 * a stale/tampered client value here can never bypass it.
 *
 * BlueCollar Live Projection Integration: `canUseBlueCollar` is the same
 * pattern, resolved from 'mlb.bluecollar_optimizer' (default ADMIN_ONLY). */
export function OptimizerWorkspace({
  initialDate = null, canUseBigMoneyMl = false, canUseBlueCollar = false,
}: { initialDate?: string | null; canUseBigMoneyMl?: boolean; canUseBlueCollar?: boolean }) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [hydrated, setHydrated] = useState(false);

  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [dateInputValue, setDateInputValue] = useState("");

  const [slates, setSlates] = useState<SlateOption[]>([]);
  // Worker-reliability fix, day-rollover safety: a persisted selectedSlateId
  // (restored from localStorage at hydration, before this component has any
  // idea whether it's still valid for today) must never trigger a pool load
  // until the slate list has actually been fetched and that ID validated --
  // otherwise a stale slate ID from a previous day/session fires a real
  // /api/optimizer/pool request before the correction below ever runs. False
  // until the first slates fetch settles (success OR failure), then stays true.
  const [slatesValidated, setSlatesValidated] = useState(false);
  const [slateStatus, setSlateStatus] = useState<string | null>(null);
  const [slateReason, setSlateReason] = useState<string | null>(null);
  const [providerIsMock, setProviderIsMock] = useState(false);
  const [slatesLoading, setSlatesLoading] = useState(true);

  const [selectedSlateId, setSelectedSlateId] = useState<string | null>(null);
  const [slateUnavailableMessage, setSlateUnavailableMessage] = useState<string | null>(null);
  const [pool, setPool] = useState<OptimizerPoolResult | null>(null);
  const [poolLoading, setPoolLoading] = useState(false);
  const [poolError, setPoolError] = useState<string | null>(null);
  const [reconcileWarnings, setReconcileWarnings] = useState<string[]>([]);

  const [locks, setLocks] = useState<string[]>([]);
  const [exclusions, setExclusions] = useState<string[]>([]);
  const [maxExposure, setMaxExposure] = useState<Record<string, number>>({});
  const [stackSize, setStackSize] = useState<number | null>(null);
  const [stackTeam, setStackTeam] = useState<string | null>(null);
  // Milestone 32.6 Part 4: set only when the current stackTeam/stackSize
  // came from a Stacks page "Use This Stack" handoff (?stackTeam=&
  // stackSize= in the URL) -- shown as a one-time confirmation banner,
  // never persisted, so a later manual edit in the Stacking panel just
  // clears it naturally without extra bookkeeping.
  const [stackHandoff, setStackHandoff] = useState<{ team: string; size: number } | null>(null);
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
  // Milestone 32.4: BIG MONEY ML COVERAGE gate -- fetched only for ADMIN,
  // only once a pool is loaded, never blocks build/validate on its own.
  const [mlCoverage, setMlCoverage] = useState<BigMoneyMlCoverage | null>(null);

  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  // Milestone 32.6 Part 2/3: pool-eligibility coverage for whichever
  // Projection Source is currently selected (any source, not just Big
  // Money ML) -- powers the "Coverage: X/Y eligible players" indicator
  // and lets the build-blocker panel below distinguish "no players have
  // this projection source yet" from a genuine roster/salary/stack
  // conflict, straight from the same --validate-only call this workspace
  // already makes.
  const [poolCoverage, setPoolCoverage] = useState<OptimizerCoverageSummary | null>(null);
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
      // Milestone 31.2C: an explicit ?date= (initialDate, resolved
      // server-side from the URL) wins over whatever date was persisted
      // from a previous session; with neither, selectedDate stays null
      // and every /api/optimizer/* call below simply omits `date`,
      // which the server resolves to Chicago-today -- identical to this
      // component's behavior before M31.2C.
      const initialSelectedDate = initialDate ?? persisted?.selectedDate ?? null;
      setSelectedDate(initialSelectedDate);
      setDateInputValue(initialSelectedDate ?? "");
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
        const persistedSource = persisted.projectionSource ?? "native";
        // A big_money_ml value persisted while ADMIN, later loaded by a
        // MEMBER (or after the flag flipped) must never silently stick --
        // fall back to native rather than surface an unreachable option.
        const persistedSourceUnreachable =
          (persistedSource === "big_money_ml" && !canUseBigMoneyMl) || (persistedSource === "bluecollar" && !canUseBlueCollar);
        setProjectionSource(persistedSourceUnreachable ? "native" : persistedSource);
        setShowProjectionComparison(persisted.showProjectionComparison ?? false);
      }
      setHydrated(true);
    });
    // Deliberately mount-once: initialDate comes from the server-rendered
    // page and is only meant to seed the very first hydration -- live
    // ?date= changes after mount are handled reactively by 1c below,
    // exactly mirroring how 1b handles ?slate= separately from any prop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  // 1c. Milestone 31.2C: same pattern as 1b, but for `?date=` -- lets a
  // link from /admin/slates' date selector (or a manual URL edit) drive
  // the Optimizer's selected date reactively after mount, not just on
  // first load.
  useEffect(() => {
    if (!hydrated) return;
    const urlDate = searchParams?.get("date");
    Promise.resolve().then(() => {
      if (urlDate && isValidSlateDateString(urlDate) && urlDate !== selectedDate) {
        setSelectedDate(urlDate);
        setDateInputValue(urlDate);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated, searchParams]);

  // 1d. Milestone 32.6 Part 4: the Stacks page's "USE THIS STACK" action
  // links here with `?stackTeam=<team>&stackSize=<n>` -- lock in a TEAM
  // stack RULE only (never specific players; Stacks only ever recommends
  // at the team level, see stacks/page.tsx), same reactive pattern as
  // 1b/1c so it applies whether this is a fresh navigation or the URL
  // changes while the page is already open. A URL stackSize of 0 or a
  // missing/blank stackTeam is ignored rather than clearing an existing
  // manual selection.
  useEffect(() => {
    if (!hydrated) return;
    const urlStackTeam = searchParams?.get("stackTeam");
    const urlStackSizeRaw = searchParams?.get("stackSize");
    const urlStackSize = urlStackSizeRaw ? Number.parseInt(urlStackSizeRaw, 10) : null;
    Promise.resolve().then(() => {
      if (urlStackTeam && urlStackSize && Number.isFinite(urlStackSize) && urlStackSize > 0) {
        if (urlStackTeam !== stackTeam || urlStackSize !== stackSize) {
          setStackTeam(urlStackTeam);
          setStackSize(urlStackSize);
        }
        setStackHandoff({ team: urlStackTeam, size: urlStackSize });
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated, searchParams]);

  // 2. Persist on every relevant change, once hydrated (never before --
  // that would clobber a saved session with fresh-mount defaults).
  useEffect(() => {
    if (!hydrated) return;
    saveWorkspaceState({
      selectedSlateId,
      selectedDate,
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
    hydrated, selectedSlateId, selectedDate, locks, exclusions, maxExposure, stackSize, stackTeam, allowPitcherVsHitter, minSalary, minUnique,
    lineups, objective, projectionSource, showProjectionComparison,
  ]);

  // 3. Discover the selected date's slates (Chicago-today when
  // selectedDate is null -- the server default, Milestone 31.2C's Part
  // 2 backward-compat contract) once, right after hydration and again
  // whenever selectedDate changes, so we know whether a persisted slate
  // selection still exists among them.
  useEffect(() => {
    if (!hydrated) return;
    Promise.resolve()
      .then(() => {
        setSlatesLoading(true);
        setSlateUnavailableMessage(null);
        setSlatesValidated(false);
        const url = selectedDate ? `/api/optimizer/slates?date=${encodeURIComponent(selectedDate)}` : "/api/optimizer/slates";
        return fetch(url);
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
          // Milestone 31.2C, Part 18 (worker-reliability fix: this check
          // must run BEFORE the "only one slate today" shortcut below --
          // it used to run after, which meant a stale persisted slate ID
          // was silently discarded with no explanation whenever today
          // happened to have exactly one real slate; a day-rollover with
          // a single Featured slate is exactly the common case). A
          // previously selected/persisted DraftGroup can genuinely
          // disappear (DraftKings rolls its live lobby, or the date
          // changed) -- surface this explicitly rather than silently
          // clearing the selection.
          if (current && !list.some((s) => s.slateId === current)) {
            setSlateUnavailableMessage("Previously selected slate is no longer available for this date. Please select another live slate below.");
            current = null;
          }
          if (current) return current;
          if (list.length === 0) return null;
          if (list.length === 1) return list[0].slateId;
          // Nothing selected yet and DraftKings published more than one
          // real Classic slate (Featured, Turbo, Afternoon, ...) -- auto-
          // pick the Main/Featured one (always the largest by game count)
          // instead of leaving the picker empty, so a first visit loads
          // real data automatically rather than waiting on a manual pick.
          const featured = list.reduce((best, s) => ((s.gameCount ?? 0) > (best.gameCount ?? 0) ? s : best), list[0]);
          return featured.slateId;
        });
        setSlatesValidated(true);
      })
      .catch(() => {
        setSlatesLoading(false);
        setSlateStatus("unavailable");
        setSlatesValidated(true);
      });
    // Runs right after hydration, and again whenever selectedDate changes
    // -- deliberately not re-run on every selectedSlateId change (that's
    // handled by the selectedSlateId effect below).
  }, [hydrated, selectedDate]);

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
          body: JSON.stringify({ slateId, date: selectedDate }),
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

        // Milestone 32.6 Part 4: a stack handed off from the Stacks page
        // (or set manually) can go stale if the slate/lineups change out
        // from under it -- reconcile by clearing it, but WARN rather than
        // silently building without the stack the user asked for.
        const teams = new Set(newPool.players.map((p) => p.team));
        const stackWarnings: string[] = [];
        if (stackTeam && !teams.has(stackTeam)) {
          stackWarnings.push(`Stack team ${stackTeam} is no longer on this slate's pool -- the stack constraint was cleared.`);
          setStackTeam(null);
          setStackHandoff(null);
        }
        setReconcileWarnings([...reconciled.warnings, ...stackWarnings]);
      })
      .catch(() => {
        setPoolLoading(false);
        setPoolError("Failed to load player pool.");
      });
  }, [locks, exclusions, maxExposure, pool, selectedDate, stackTeam]);

  useEffect(() => {
    // slatesValidated: never load a pool for a selectedSlateId that
    // hasn't been confirmed present in a freshly-fetched slate list yet
    // -- a persisted-from-localStorage ID restored at hydration is not
    // trustworthy until this component has actually checked it (see
    // setSlatesValidated's own comment above).
    if (!hydrated || !selectedSlateId || !slatesValidated) return;
    loadPool(selectedSlateId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated, selectedSlateId, selectedDate, slatesValidated]);

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
      date: selectedDate,
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
    pool, locks, exclusions, maxExposure, selectedSlateId, selectedDate, lineups, objective, stackSize, stackTeam, allowPitcherVsHitter, minSalary,
    minUnique, projectionSource,
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
    const fantasyProsUnavailable = projectionSource === "fantasypros" && !pool.hasFantasyProsProjections;
    // Milestone 32.4: also falls back if the ADMIN's browser somehow has
    // big_money_ml persisted but this slate has no ML coverage yet, or
    // if canUseBigMoneyMl became false (e.g. flag flipped mid-session).
    const mlUnavailable = projectionSource === "big_money_ml" && (!canUseBigMoneyMl || !pool.hasMlProjections);
    // BlueCollar: same fallback pattern -- also falls back if the
    // ADMIN's browser somehow has bluecollar persisted but this slate
    // has no BlueCollar coverage yet, or canUseBlueCollar became false.
    const blueCollarUnavailable = projectionSource === "bluecollar" && (!canUseBlueCollar || !pool.hasBlueCollarProjections);
    if (externalUnavailable || aiUnavailable || nativeUnavailable || fantasyProsUnavailable || mlUnavailable || blueCollarUnavailable) {
      Promise.resolve().then(() => setProjectionSource("independent"));
    }
  }, [pool, projectionSource, canUseBigMoneyMl, canUseBlueCollar]);

  // Milestone 32.4: BIG MONEY ML COVERAGE gate -- ADMIN-only, fetched
  // once a pool is loaded so the coverage numbers are ready the moment
  // the option is offered (not only after selecting it).
  useEffect(() => {
    if (!canUseBigMoneyMl || !pool || !selectedSlateId) {
      Promise.resolve().then(() => setMlCoverage(null));
      return;
    }
    let cancelled = false;
    const params = new URLSearchParams({ slateId: selectedSlateId });
    if (selectedDate) params.set("date", selectedDate);
    fetch(`/api/optimizer/ml-coverage?${params.toString()}`)
      .then((res) => res.json())
      .then((body) => {
        if (!cancelled) setMlCoverage(body?.coverage ?? null);
      })
      .catch(() => {
        if (!cancelled) setMlCoverage(null);
      });
    return () => {
      cancelled = true;
    };
  }, [canUseBigMoneyMl, pool, selectedSlateId, selectedDate]);

  // 5. Debounced, authoritative pre-solve validation (reuses the real
  // optimizer's own resolve_settings()/pre_solve_diagnostics() via
  // /api/optimizer/validate -- never the CP-SAT solver).
  useEffect(() => {
    if (!pool) {
      Promise.resolve().then(() => {
        setValidationErrors([]);
        setPoolCoverage(null);
      });
      return;
    }
    const handle = setTimeout(() => {
      fetch("/api/optimizer/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildRequestBody()),
      })
        .then((res) => res.json())
        .then((data) => {
          setValidationErrors(data.errors ?? []);
          setPoolCoverage(data.coverage ?? null);
        })
        .catch(() => {
          setValidationErrors([]);
          setPoolCoverage(null);
        });
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

  // Milestone 31.2C, Part 4/7: committing a date navigates to
  // ?date=... (persists across a page refresh, Part 7) -- 1c above then
  // picks up the URL change and updates selectedDate, which in turn
  // re-fetches the slate list for that date (effect 3).
  function commitDateChange(nextDate: string) {
    if (!isValidSlateDateString(nextDate) || nextDate === selectedDate) return;
    router.push(`/dashboard/optimizer?date=${encodeURIComponent(nextDate)}`);
  }

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
          Slate Date:
          <input
            type="date"
            value={dateInputValue}
            onChange={(e) => setDateInputValue(e.target.value)}
            onBlur={() => dateInputValue && commitDateChange(dateInputValue)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && dateInputValue) commitDateChange(dateInputValue);
            }}
            title="Defaults to today's America/Chicago date -- set explicitly if DraftKings' live lobby has already rolled to the next calendar day"
            className="rounded border border-border bg-bg-panel-raised px-2 py-1 text-text"
          />
        </label>

        <label className="flex items-center gap-2 text-xs text-text-muted">
          Slate:
          <select
            value={selectedSlateId ?? ""}
            onChange={(e) => {
              setSelectedSlateId(e.target.value || null);
              setSlateUnavailableMessage(null);
            }}
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

        {pool && (
          <span className="rounded bg-bg-panel-raised px-2 py-1 text-[11px] font-medium text-text" title="The slate/date this player pool and any lineups you build will use">
            Active Slate: MLB -- {pool.slateName ?? pool.slateId} -- {pool.date} -- {pool.slateGames} Games
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
              ...(canUseBigMoneyMl ? [{ value: "big_money_ml" as ProjectionSource, label: "Big Money ML" }] : []),
              // "BlueCollar Live" -- deliberately NOT the bare "BlueCollar"
              // label: the pre-existing "external"/"adjusted" comparison
              // source (Milestone 17/27, external_projections/registry.py)
              // already defaults ITS OWN label to plain "BlueCollar" via
              // resolveExternalSourceLabel() whenever no baseline provider
              // is configured -- a real naming collision two buttons would
              // otherwise share. This button is the live, purpose-built
              // bluecollar/ package integration; "Live" disambiguates it
              // from that separate, older, CSV/registry-based mechanism.
              ...(canUseBlueCollar ? [{ value: "bluecollar" as ProjectionSource, label: "BlueCollar Live" }] : []),
              { value: "external" as ProjectionSource, label: externalSourceLabel },
              { value: "adjusted" as ProjectionSource, label: `${externalSourceLabel} (Adjusted)` },
              { value: "fantasypros" as ProjectionSource, label: "FantasyPros" },
              { value: "independent" as ProjectionSource, label: "Legacy" },
            ]
          ).map((opt) => {
            const disabled =
              opt.value === "ai" ? !pool?.hasAiProjections
              : opt.value === "native" ? !pool?.hasNativeProjections
              : opt.value === "fantasypros" ? !pool?.hasFantasyProsProjections
              : opt.value === "big_money_ml" ? !pool?.hasMlProjections
              : opt.value === "bluecollar" ? !pool?.hasBlueCollarProjections
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
                      : opt.value === "big_money_ml" || opt.value === "bluecollar"
                        ? "bg-yellow/20 text-yellow"
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
        {!pool?.hasFantasyProsProjections && (
          <span className="text-[11px] text-text-faint">FantasyPros not available -- not configured, no matched players, or not fetched yet.</span>
        )}
        {canUseBigMoneyMl && !pool?.hasMlProjections && (
          <span className="text-[11px] text-text-faint">Big Money ML not generated yet for this slate -- run the shadow-inference step during Process/Refresh.</span>
        )}
        {canUseBlueCollar && pool && !pool.hasBlueCollarProjections && (
          <span className="text-[11px] text-text-faint">
            {pool.blueCollarSlateMatchStatus && pool.blueCollarSlateMatchStatus !== "matched"
              ? "BLUECOLLAR NOT UPDATED -- slate match failed for this DK slate."
              : "BlueCollar not fetched yet for this slate -- run Admin Refresh Data."}
          </span>
        )}
        {/* Freshness status (per spec: never make the user wonder whether
            the data loaded) -- shown whenever a BlueCollar snapshot
            exists for this slate, regardless of which source is
            currently selected. */}
        {canUseBlueCollar && pool?.hasBlueCollarProjections && (
          <span className="w-full text-[11px] text-text-faint">
            BLUECOLLAR &middot; {pool.blueCollarSlateName ?? "matched slate"} &middot; UPDATED {pool.blueCollarUpdated ?? "--"}
          </span>
        )}

        {PROJECTION_SOURCE_EXPLANATIONS[projectionSource] && (
          <span className="w-full text-[11px] text-text-faint">{PROJECTION_SOURCE_EXPLANATIONS[projectionSource]}</span>
        )}
        {/* Milestone 32.6 Part 3: coverage for whichever source is
            currently selected -- from the same --validate-only call this
            workspace already debounces, never a second/extra fetch. */}
        {pool && poolCoverage && (
          <span className={`w-full text-[11px] ${poolCoverage.usableForBuild < poolCoverage.optimizerEligible ? "text-yellow" : "text-text-faint"}`}>
            Coverage: {poolCoverage.usableForBuild}/{poolCoverage.optimizerEligible} eligible players
            {poolCoverage.usableForBuild < poolCoverage.optimizerEligible &&
              ` -- ${poolCoverage.optimizerEligible - poolCoverage.usableForBuild} eligible player(s) missing a ${
                poolCoverage.strictSource ? poolCoverage.projectionSource : "usable"
              } projection${poolCoverage.strictSource ? " (strict source, never mixed)" : ""}.`}
          </span>
        )}

        <label className="ml-auto flex items-center gap-1.5 text-xs text-text-muted">
          <input type="checkbox" checked={showProjectionComparison} onChange={(e) => setShowProjectionComparison(e.target.checked)} />
          Show comparison columns
        </label>
      </div>

      {/* Milestone 32.4: BIG MONEY ML COVERAGE gate + EXPERIMENTAL/OWNER
          TEST labeling -- shown only once big_money_ml is actually the
          selected source, informational only (never blocks the build by
          itself; strict-source exclusion + roster feasibility diagnostics
          handle that if coverage is too thin). */}
      {projectionSource === "big_money_ml" && (
        <div className="rounded-[var(--radius-card)] border border-yellow/40 bg-yellow/5 p-3 text-xs shadow-[var(--shadow-card)]">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="rounded bg-yellow/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-yellow">Experimental</span>
            <span className="rounded bg-yellow/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-yellow">Owner Test</span>
            <span className="font-medium text-text">Big Money ML</span>
            {mlCoverage && (
              <span className="text-text-faint">
                Pitchers v{mlCoverage.pitcherModelVersion ?? "--"} &middot; Hitters v{mlCoverage.hitterModelVersion ?? "--"}
              </span>
            )}
          </div>
          {mlCoverage ? (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <StatusStat label="Pitchers" value={`${mlCoverage.pitchers.generated}/${mlCoverage.pitchers.eligible}`} />
              <StatusStat label="Hitters" value={`${mlCoverage.hitters.generated}/${mlCoverage.hitters.eligible}`} />
              <StatusStat label="Combined" value={`${mlCoverage.combined.generated}/${mlCoverage.combined.eligible}`} />
              <StatusStat label="Games Waiting For Lineups" value={mlCoverage.gamesWaitingForLineups} />
            </div>
          ) : (
            <p className="text-text-faint">Loading ML coverage...</p>
          )}
          <p className="mt-2 text-[11px] text-text-faint">
            ML-only means ML-only: any optimizer-eligible player without a valid pregame ML projection is EXCLUDED from this build, never
            silently mixed with Native/AI/FantasyPros/Legacy.
          </p>
        </div>
      )}

      {/* BlueCollar Live Projection Integration: shown only once
          bluecollar is actually the selected source. Coverage numbers
          come from the same generic poolCoverage line above (Part 3) --
          this box adds only the strict-source reminder + freshness. */}
      {projectionSource === "bluecollar" && (
        <div className="rounded-[var(--radius-card)] border border-yellow/40 bg-yellow/5 p-3 text-xs shadow-[var(--shadow-card)]">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="rounded bg-yellow/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-yellow">Admin Test</span>
            <span className="font-medium text-text">BlueCollar</span>
            {pool?.blueCollarSlateName && <span className="text-text-faint">{pool.blueCollarSlateName}</span>}
            {pool?.blueCollarUpdated && <span className="text-text-faint">&middot; Updated {pool.blueCollarUpdated}</span>}
          </div>
          <p className="text-[11px] text-text-faint">
            BlueCollar-only means BlueCollar-only: any optimizer-eligible player without a genuinely usable (matched, positive) BlueCollar
            projection is EXCLUDED from this build, never silently mixed with Native/AI/ML/Legacy.
          </p>
        </div>
      )}

      {/* Milestone 32.6 Part 4: visible confirmation after a Stacks page
          "Use This Stack" handoff -- a TEAM STACK RULE only, never
          specific locked players (see stacks/page.tsx's own docstring). */}
      {stackHandoff && stackTeam === stackHandoff.team && stackSize === stackHandoff.size && (
        <div className="rounded border border-accent bg-accent-dim px-3 py-2 text-xs text-text">
          <span className="font-semibold uppercase tracking-wide">
            Stack: {stackHandoff.team} &times;{stackHandoff.size}
          </span>{" "}
          <span className="text-text-muted">applied from Stacks. Team stack rule only -- no specific players were locked.</span>
        </div>
      )}

      {slateUnavailableMessage && (
        <div className="rounded border border-yellow bg-bg-panel-raised px-3 py-2 text-xs text-yellow">{slateUnavailableMessage}</div>
      )}
      {slateStatus && slateStatus !== "ready" && (
        <div className="rounded border border-red bg-bg-panel-raised px-3 py-2 text-xs text-red">
          {SLATE_STATUS_MESSAGES[slateStatus] ?? slateReason ?? `Slate status: ${slateStatus}`}
        </div>
      )}
      {poolError && <div className="rounded border border-red bg-bg-panel-raised px-3 py-2 text-xs text-red">{poolError}</div>}
      {reconcileWarnings.length > 0 && (
        <div className="rounded border border-yellow bg-bg-panel-raised px-3 py-2 text-xs text-yellow">{reconcileWarnings.join(" ")}</div>
      )}
      {/* Worker-reliability fix: a real, reused-but-stale DraftKings
          artifact (>15 min old, still within the safe reuse ceiling)
          never blocks the optimizer -- just an honest, visible notice.
          Never shown when the data is fresh. */}
      {pool && pool.dataStatus === "stale" && (
        <div className="rounded border border-yellow bg-bg-panel-raised px-3 py-2 text-xs text-yellow">
          DraftKings data last updated {formatAgeMinutes(pool.artifactAgeSeconds)} ago.
        </div>
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
            onStackSizeChange={(size) => {
              setStackHandoff(null);
              setStackSize(size);
            }}
            onStackTeamChange={(team) => {
              setStackHandoff(null);
              setStackTeam(team);
            }}
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

function StatusStat({ label, value }: { label: string; value: number | string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-text-faint">{label}</div>
      <div className="text-sm font-semibold text-text">{value}</div>
    </div>
  );
}
