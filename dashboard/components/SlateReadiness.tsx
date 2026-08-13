"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import type { ArtifactReadiness } from "@/lib/orchestrator/artifactStatus";
import type { PipelineStepId, RunState } from "@/lib/orchestrator/types";

const POLL_INTERVAL_MS = 1500;

const ROWS: Array<{ id: PipelineStepId; label: string }> = [
  { id: "research", label: "Research" },
  { id: "pitchers", label: "Pitchers" },
  { id: "batters", label: "Hitters" },
  { id: "dfsSalaries", label: "DFS Salaries" },
  { id: "playerPool", label: "Player Pool" },
  { id: "ownership", label: "Ownership" },
  { id: "optimizer", label: "Optimizer" },
];

/** Compact "at a glance" readiness summary for the main dashboard
 * (Milestone 16). `readiness` is computed server-side by
 * lib/orchestrator/artifactStatus.ts (a pure filesystem read, passed in
 * as a prop) so this component never has to duplicate that logic. The
 * "Refresh Missing Data" button starts the same centralized smart
 * (missing-data-only) orchestrator run used everywhere else, targeting
 * the optimizer's full dependency closure -- already-ready steps are
 * skipped, not rebuilt. Hidden entirely once everything is ready. */
export function SlateReadiness({ readiness }: { readiness: ArtifactReadiness }) {
  const router = useRouter();
  const [run, setRun] = useState<RunState | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [readyNotified, setReadyNotified] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(() => {
    fetch("/api/refresh")
      .then((res) => res.json())
      .then((data) => setRun(data.run ?? null))
      .catch(() => {
        // Transient fetch failure while polling -- leave the last known state on screen.
      });
  }, []);

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

  useEffect(() => {
    if (run?.status !== "completed" || readyNotified) return;
    Promise.resolve().then(() => {
      setReadyNotified(true);
      router.refresh();
      // Fall back to the (now-stale-but-about-to-be-revalidated) readiness
      // prop instead of holding onto this finished run's step list forever.
      setRun(null);
    });
  }, [run?.status, readyNotified, router]);

  function handleRefreshMissing() {
    setStarting(true);
    setError(null);
    setReadyNotified(false);
    fetch("/api/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ targetSteps: ["optimizer"], smart: true }),
    })
      .then((res) => res.json())
      .then((data) => {
        setStarting(false);
        if (data.error && !data.run) {
          setError(data.error);
          return;
        }
        setRun(data.run ?? null);
      })
      .catch(() => {
        setStarting(false);
        setError("Failed to start -- is the dashboard server running?");
      });
  }

  const allReady = ROWS.every((row) => readiness[row.id]);
  const isActive = run?.status === "running" || run?.status === "needs_selection";

  return (
    <div className="mb-6 rounded-lg border border-border bg-bg-panel p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-text-muted">Slate Readiness</h2>
        {allReady && !isActive && <span className="text-xs font-semibold text-green">ALL SYSTEMS READY</span>}
        {!allReady && (
          <button
            type="button"
            onClick={handleRefreshMissing}
            disabled={starting || isActive}
            className="rounded border border-accent bg-accent-dim px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-text disabled:cursor-not-allowed disabled:opacity-60"
          >
            {starting || isActive ? "Refreshing..." : "Refresh Missing Data"}
          </button>
        )}
      </div>

      {error && <div className="mb-3 rounded border border-red bg-bg-panel-raised px-3 py-2 text-xs text-red">{error}</div>}

      <div className="grid grid-cols-2 gap-2 text-xs md:grid-cols-4 lg:grid-cols-7">
        {ROWS.map((row) => {
          const stepResult = run?.steps.find((s) => s.id === row.id);
          const running = stepResult?.status === "running";
          const ready = stepResult ? stepResult.status === "ready" : readiness[row.id];
          return (
            <div key={row.id} className="flex items-center justify-between gap-2 rounded border border-border-subtle bg-bg-panel-raised px-2 py-1.5">
              <span className="text-text-faint">{row.label}</span>
              <span className={`font-semibold uppercase tracking-wide ${running ? "text-accent" : ready ? "text-green" : "text-red"}`}>
                {running ? "RUNNING" : ready ? "READY" : "MISSING"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
