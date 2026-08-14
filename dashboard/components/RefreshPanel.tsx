"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { DraftKingsCsvUpload } from "./DraftKingsCsvUpload";
import { PrimaryButton, SecondaryButton } from "./ui/Button";
import { ProviderStatusCard } from "./ProviderStatusCard";
import { SlateSelector } from "./SlateSelector";
import { getTodayChicagoDate } from "@/lib/currentDate";
import type { ChangeReport, RunOutcome, RunState, RunSummary, StepStatus } from "@/lib/orchestrator/types";

const POLL_INTERVAL_MS = 1500;

/** Mirrors dfs/providers/config.py::NO_PROVIDER_CONFIGURED_MESSAGE
 * exactly -- when a failed run's error is precisely this string (never
 * merely the same outcome, e.g. an explicit misconfiguration also maps
 * to "dfs_not_connected"), the panel shows the "Import CSV" /
 * "Enable Mock Mode" choice instead of a plain error, per Milestone
 * 19's VALIDATION requirement. */
const NO_PROVIDER_CONFIGURED_MESSAGE = "No live DraftKings salary provider configured.";

const STEP_STYLES: Record<StepStatus, { dot: string; text: string; label: string }> = {
  waiting: { dot: "bg-text-faint", text: "text-text-faint", label: "WAITING" },
  running: { dot: "bg-accent", text: "text-accent", label: "RUNNING" },
  ready: { dot: "bg-green", text: "text-green", label: "READY" },
  failed: { dot: "bg-red", text: "text-red", label: "FAILED" },
  needs_input: { dot: "bg-yellow", text: "text-yellow", label: "NEEDS INPUT" },
  skipped: { dot: "bg-text-faint", text: "text-text-faint", label: "SKIPPED" },
};

const OUTCOME_MESSAGES: Partial<Record<RunOutcome, string>> = {
  mlb_data_failure: "MLB data failure -- the research package could not be built.",
  pitcher_agent_failure: "Pitcher Agent run failed.",
  batter_agent_failure: "Batter Agent run failed.",
  // Milestone 19: this generic fallback only renders for a genuine explicit
  // misconfiguration (DFS_SALARY_PROVIDER set to an unrecognized value) --
  // the far more common "nothing configured yet" case is caught separately
  // below (run.error === NO_PROVIDER_CONFIGURED_MESSAGE) and shown with the
  // Import CSV / Enable Mock Mode choice instead of this text.
  dfs_not_connected: "DFS SALARIES NOT CONNECTED -- DFS_SALARY_PROVIDER is set to an unrecognized value.",
  dfs_unavailable: "DFS salary provider unavailable.",
  dfs_auth_failed: "DFS salary provider authentication failed.",
  dfs_no_slate: "DFS salary provider returned no slate for today.",
  dfs_invalid_slate_id: "The selected DFS slate id was not valid.",
  player_matching_failure: "Player matching failure -- too few DFS entries matched MLB identities to continue.",
  roster_infeasible: "Roster infeasible -- the matched player pool cannot fill a legal DK roster.",
  ownership_failure: "Ownership projection failed.",
  optimizer_infeasible: "The optimizer could not produce lineups for one or more objectives.",
  unexpected_error: "An unexpected error stopped the refresh.",
};

function stepLabel(run: RunState): string {
  return run.steps.find((s) => s.id === run.currentStepId)?.label ?? "";
}

/** Milestone 19: the Big Money Research Adjustment Layer is re-run
 * best-effort on every refresh (see runner.ts::runExternalProjectionRefresh)
 * -- "no baseline yet" (nothing imported under Settings -> External Data)
 * is a normal state, not a failure, so it reads as a neutral "Not
 * Imported" rather than an error. */
function externalProjectionStatusLabel(summary: RunSummary): string {
  switch (summary.externalProjectionStatus) {
    case "ready":
      return `READY (${summary.externalProjectionRecordCount ?? 0} players)`;
    case "no_baseline":
      return "Not Imported";
    case "no_research":
      return "Waiting on Research";
    case "error":
      return "Refresh Failed";
    case "not_attempted":
    default:
      return "--";
  }
}

/** The one-click "REFRESH TODAY'S SLATE" control: starts/monitors a
 * pregame pipeline run on the Node orchestrator (lib/orchestrator/) and
 * renders its live per-step status, DFS provider connectivity, a slate
 * picker when the provider exposes more than one, the full completion
 * summary, and the change report vs. the previous refresh. Polls
 * /api/refresh only while a run is active. */
export function RefreshPanel() {
  const [run, setRun] = useState<RunState | null>(null);
  const [starting, setStarting] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [enablingMock, setEnablingMock] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Deliberately .then()-chained rather than async/await: an async function
  // that awaits then calls a state setter reads, to React's effect-analysis
  // lint rule, as "setState synchronously in an effect" when invoked from
  // one below -- this shape (fetch -> then -> setState) is the pattern it
  // recognizes as safe external-data synchronization.
  const fetchStatus = useCallback(() => {
    fetch("/api/refresh")
      .then((res) => res.json())
      .then((data) => setRun(data.run ?? null))
      .catch(() => {
        // Transient fetch failure while polling -- leave the last known state on screen.
      });
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  useEffect(() => {
    const active = run?.status === "running" || run?.status === "needs_selection";
    if (active && !pollRef.current) {
      pollRef.current = setInterval(fetchStatus, POLL_INTERVAL_MS);
    }
    if (!active && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [run?.status, fetchStatus]);

  async function handleRefresh() {
    setStarting(true);
    setError(null);
    try {
      const res = await fetch("/api/refresh", { method: "POST" });
      const data = await res.json();
      if (res.status === 409) setError(data.error ?? "A refresh is already in progress.");
      setRun(data.run ?? null);
    } catch {
      setError("Failed to start the refresh -- is the dashboard server running?");
    } finally {
      setStarting(false);
    }
  }

  async function handleEnableMockMode() {
    setEnablingMock(true);
    setError(null);
    try {
      const res = await fetch("/api/settings/mock-mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: true }),
      });
      if (!res.ok) {
        const data = await res.json();
        setError(data.error ?? "Failed to enable Mock Mode.");
        return;
      }
      await handleRefresh();
    } catch {
      setError("Failed to enable Mock Mode.");
    } finally {
      setEnablingMock(false);
    }
  }

  async function handleSelectSlate(slateId: string) {
    setSelecting(true);
    setError(null);
    try {
      const res = await fetch("/api/refresh/select-slate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slateId }),
      });
      const data = await res.json();
      if (!res.ok) setError(data.error ?? "Failed to select that slate.");
      else setRun(data.run ?? null);
    } catch {
      setError("Failed to select that slate.");
    } finally {
      setSelecting(false);
    }
  }

  const isRunning = run?.status === "running";
  const isPaused = run?.status === "needs_selection";
  const busy = starting || isRunning;

  return (
    <div className="mb-6 flex flex-col gap-4 rounded-lg border border-border bg-bg-panel p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">Today&apos;s Slate</h1>
          {run && <p className="text-xs text-text-faint">Slate date: {run.slateDate}</p>}
        </div>
        <button
          type="button"
          onClick={handleRefresh}
          disabled={busy}
          className="rounded border border-accent bg-accent-dim px-4 py-2 text-xs font-semibold uppercase tracking-wide text-text disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy ? (run && isRunning ? `Running: ${stepLabel(run)}...` : "Starting...") : "Refresh Today's Slate"}
        </button>
        <SecondaryButton type="button" onClick={() => setShowUpload((v) => !v)}>
          {showUpload ? "Hide Upload" : "Upload DraftKings CSV"}
        </SecondaryButton>
      </div>

      {error && <div className="rounded border border-red bg-bg-panel-raised px-3 py-2 text-xs text-red">{error}</div>}

      <ProviderStatusCard summary={run?.summary ?? null} dfsStep={run?.steps.find((s) => s.id === "dfsSalaries") ?? null} />

      {run && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-7">
          {run.steps.map((step) => {
            const style = STEP_STYLES[step.status];
            return (
              <div key={step.id} className="flex flex-col gap-1 rounded border border-border-subtle bg-bg-panel-raised p-3">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] uppercase tracking-wide text-text-muted">{step.label}</span>
                  <span className={`h-2 w-2 rounded-full ${style.dot}`} />
                </div>
                <span className={`text-xs font-semibold ${style.text}`}>{style.label}</span>
                {step.message && <span className="text-[11px] text-text-faint">{step.message}</span>}
              </div>
            );
          })}
        </div>
      )}

      {isPaused && run?.slateOptions && <SlateSelector options={run.slateOptions} onSelect={handleSelectSlate} disabled={selecting} />}

      {run?.status === "failed" && run.outcome && run.error !== NO_PROVIDER_CONFIGURED_MESSAGE && (
        <div className="rounded border border-red bg-bg-panel-raised px-3 py-2 text-xs text-red">
          {OUTCOME_MESSAGES[run.outcome] ?? run.outcome}
          {run.error && <div className="mt-1 text-text-faint">{run.error}</div>}
        </div>
      )}

      {run?.status === "failed" && run.error === NO_PROVIDER_CONFIGURED_MESSAGE && (
        <div className="rounded border border-yellow bg-bg-panel-raised p-3">
          <div className="text-xs font-semibold text-yellow">{NO_PROVIDER_CONFIGURED_MESSAGE}</div>
          <p className="mt-1 text-[11px] text-text-faint">
            Upload today&apos;s real DraftKings salary CSV, or turn on Mock Mode for development/testing.
          </p>
          <div className="mt-2 flex gap-2">
            <PrimaryButton type="button" onClick={() => setShowUpload((v) => !v)}>
              Import CSV
            </PrimaryButton>
            <SecondaryButton type="button" onClick={handleEnableMockMode} disabled={enablingMock}>
              {enablingMock ? "Enabling..." : "Enable Mock Mode"}
            </SecondaryButton>
          </div>
        </div>
      )}

      {showUpload && (
        <DraftKingsCsvUpload
          date={run?.slateDate ?? getTodayChicagoDate()}
          onUploaded={() => {
            setShowUpload(false);
            handleRefresh();
          }}
        />
      )}

      {run?.status === "completed" && run.summary && <RunSummaryBlock summary={run.summary} />}
      {run?.changeReport && <ChangeReportBlock report={run.changeReport} />}
    </div>
  );
}

function RunSummaryBlock({ summary }: { summary: RunSummary }) {
  const rows: Array<[string, string | number]> = [
    ["MLB Games", summary.mlbGames ?? "--"],
    ["DFS Games", summary.dfsGames ?? "--"],
    ["Posted DFS Lineups", summary.postedLineups ?? "--"],
    ["Missing DFS Lineups", summary.missingLineups ?? "--"],
    ["Pitchers", summary.pitcherCount ?? "--"],
    ["Hitters", summary.hitterCount ?? "--"],
    ["Salary Coverage", summary.salaryCoveragePercent != null ? `${summary.salaryCoveragePercent}%` : "--"],
    ["Position Coverage", summary.positionCoveragePercent != null ? `${summary.positionCoveragePercent}%` : "--"],
    ["Ownership", summary.ownershipReady ? "READY" : "--"],
    ["External Projections", externalProjectionStatusLabel(summary)],
  ];

  return (
    <div className="rounded border border-green bg-bg-panel-raised p-3">
      <div className="mb-2 text-sm font-semibold text-green">LIVE SLATE READY</div>
      <div className="grid grid-cols-2 gap-2 text-xs md:grid-cols-3">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-2 border-b border-border-subtle pb-1">
            <span className="text-text-faint">{label}</span>
            <span className="text-text">{value}</span>
          </div>
        ))}
      </div>
      <div className="mt-2 text-xs text-text-faint">
        Lineups -- Projection: {summary.lineupCounts.projection ?? "--"}, Balanced: {summary.lineupCounts.balanced ?? "--"}, Leverage:{" "}
        {summary.lineupCounts.leverage ?? "--"}
      </div>
    </div>
  );
}

function ChangeReportBlock({ report }: { report: ChangeReport }) {
  if (!report.previousRunId) {
    return (
      <div className="rounded border border-border-subtle bg-bg-panel-raised p-3 text-xs text-text-faint">
        {report.notes[0] ?? "No prior refresh to compare against."}
      </div>
    );
  }

  return (
    <div className="rounded border border-border-subtle bg-bg-panel-raised p-3">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Change Since Last Refresh</div>
      <div className="grid grid-cols-2 gap-2 text-xs md:grid-cols-3">
        <div className="text-text-faint">
          New posted lineups: <span className="text-text">{report.newPostedLineupGames ?? "--"}</span>
        </div>
        <div className="text-text-faint">
          Salary changes: <span className="text-text">{report.salaryChangedCount ?? "--"}</span>
        </div>
        <div className="text-text-faint">
          Projection changes: <span className="text-text">{report.projectionChangedCount ?? "--"}</span>
        </div>
        <div className="text-text-faint">
          Ownership changes: <span className="text-text">{report.ownershipChangedCount ?? "--"}</span>
        </div>
        <div className="text-text-faint">
          Scratches: <span className="text-text">{report.scratches.length}</span>
        </div>
        <div className="text-text-faint">
          Starter changes: <span className="text-text">{report.starterChanges.length}</span>
        </div>
      </div>
      {report.scratches.length > 0 && <div className="mt-2 text-xs text-red">Scratched: {report.scratches.join(", ")}</div>}
      {report.starterChanges.length > 0 && <div className="mt-1 text-xs text-yellow">{report.starterChanges.join("; ")}</div>}
      {report.exposureChanges.length > 0 && (
        <div className="mt-2 text-xs text-text-faint">
          Exposure changes:{" "}
          {report.exposureChanges
            .slice(0, 5)
            .map((c) => `${c.name} ${c.beforePercent ?? 0}%->${c.afterPercent ?? 0}%`)
            .join(", ")}
        </div>
      )}
      {report.notes.length > 0 && <div className="mt-2 text-[11px] text-text-faint">{report.notes.join(" ")}</div>}
    </div>
  );
}
