"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { PrimaryButton } from "@/components/ui/Button";
import type { PipelineStepId, RunState, StepStatus } from "@/lib/orchestrator/types";

const POLL_INTERVAL_MS = 1500;

const STEP_STYLES: Record<StepStatus, { text: string; label: string }> = {
  waiting: { text: "text-text-faint", label: "WAITING" },
  running: { text: "text-accent", label: "RUNNING" },
  ready: { text: "text-green", label: "READY" },
  failed: { text: "text-red", label: "FAILED" },
  needs_input: { text: "text-yellow", label: "NEEDS INPUT" },
  skipped: { text: "text-text-faint", label: "SKIPPED" },
};

/** A reusable "this data isn't ready yet" empty state that replaces raw
 * `python scripts/...` command instructions everywhere in the dashboard
 * (Milestone 16). Shows a plain-language title/description and a single
 * button; clicking it starts a "smart" (missing-data-only) refresh
 * scoped to `targetSteps` via the same centralized orchestrator every
 * other refresh action already uses (lib/orchestrator/runner.ts) --
 * nothing here spawns its own process or duplicates command logic.
 * Progress is shown as a short list of just the steps in that target's
 * dependency chain (already-skipped steps are hidden). On success, the
 * current route is revalidated automatically (no manual browser
 * refresh) unless the caller supplies its own `onReady`. */
export function MissingDataState({
  title,
  description,
  primaryActionLabel,
  targetSteps,
  onReady,
}: {
  title: string;
  description: string;
  primaryActionLabel: string;
  targetSteps: PipelineStepId[];
  onReady?: () => void;
}) {
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

  // Deferred one microtask so the setState call happens inside a callback
  // rather than the effect's synchronous body -- satisfies
  // react-hooks/set-state-in-effect (see OptimizerWorkspace.tsx).
  useEffect(() => {
    if (run?.status !== "completed" || readyNotified) return;
    Promise.resolve().then(() => {
      setReadyNotified(true);
      if (onReady) onReady();
      else router.refresh();
    });
  }, [run?.status, readyNotified, onReady, router]);

  function handleClick() {
    setStarting(true);
    setError(null);
    setReadyNotified(false);
    fetch("/api/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ targetSteps, smart: true }),
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

  const relevantSteps = (run?.steps ?? []).filter((s) => s.status !== "skipped");
  const isActive = run?.status === "running" || run?.status === "needs_selection";

  if (isActive) {
    return (
      <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-6 text-sm shadow-[var(--shadow-card)]">
        <div className="mb-3 font-medium text-text">Generating...</div>
        <div className="flex flex-col gap-2">
          {relevantSteps.map((step) => {
            const style = STEP_STYLES[step.status];
            return (
              <div key={step.id} className="flex items-center justify-between text-xs">
                <span className="text-text-muted">{step.label}</span>
                <span className={`font-semibold uppercase tracking-wide ${style.text}`}>{style.label}</span>
              </div>
            );
          })}
        </div>
        {run?.status === "needs_selection" && (
          <p className="mt-3 text-xs text-yellow">
            Multiple DFS slates were found. Open the Optimizer page to choose one, then try again.
          </p>
        )}
      </div>
    );
  }

  if (run?.status === "failed") {
    return (
      <div className="rounded-[var(--radius-card)] border border-red bg-bg-panel p-6 text-sm shadow-[var(--shadow-card)]">
        <div className="mb-1 font-medium text-text">{title}</div>
        <p className="mb-3 text-text-faint">{description}</p>
        <div className="mb-3 rounded-[var(--radius-control)] border border-red bg-bg-panel-raised px-3 py-2 text-xs text-red">
          {relevantSteps.find((s) => s.status === "failed")?.message ?? run.error ?? "The last attempt failed."}
        </div>
        <PrimaryButton onClick={handleClick} disabled={starting} className="uppercase tracking-wide">
          Try Again
        </PrimaryButton>
      </div>
    );
  }

  return (
    <div className="rounded-[var(--radius-card)] border border-dashed border-border bg-bg-panel p-8 text-center text-sm shadow-[var(--shadow-card)]">
      <div className="mb-2 text-2xl" aria-hidden="true">
        📊
      </div>
      <div className="mb-1 font-medium text-text">{title}</div>
      <p className="mb-4 text-text-faint">{description}</p>
      {error && <p className="mb-3 text-xs text-red">{error}</p>}
      <PrimaryButton onClick={handleClick} disabled={starting} className="uppercase tracking-wide">
        {starting ? "Starting..." : primaryActionLabel}
      </PrimaryButton>
    </div>
  );
}
