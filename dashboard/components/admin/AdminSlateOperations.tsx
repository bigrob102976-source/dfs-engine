"use client";

import { useCallback, useEffect, useState } from "react";

import { DraftKingsMultiCsvUpload } from "@/components/DraftKingsMultiCsvUpload";
import { PrimaryButton, SecondaryButton } from "@/components/ui/Button";

interface ReadinessCheck {
  key: string;
  label: string;
  ok: boolean;
  detail: string;
}

interface ActiveJob {
  id: string;
  jobType: string;
  status: string;
  progress: number;
  currentStep: string | null;
}

interface EligibilityCounts {
  raw_dk_players: number;
  starting_pitchers: number;
  relief_pitchers: number;
  confirmed_hitters: number;
  bench_hitters: number;
  waiting_for_lineups: number;
  scratched: number;
  unmatched: number;
  ambiguous: number;
  optimizer_eligible: number;
}

// Canonical MLB Player Identity Foundation: PLAYER IDENTITY, shown
// separately from eligibility below -- "does this DK row resolve to a
// real mlb_player_id" is a different question from "is this player
// optimizer-buildable today."
interface IdentityCounts {
  dk_entries: number;
  resolved: number;
  ambiguous: number;
  unmatched: number;
}

// M32.7: BlueCollar's own funnel, always separate counts -- see
// lib/blueCollarProjections.ts::computeBlueCollarCoverage.
interface BlueCollarCoverage {
  returned: number;
  usable: number;
  identityResolved: number;
  eligible: number;
  optimizerReady: number;
}

// M32.7: "After Refresh Data, show what changed" -- see
// lib/slateChangeReport.ts.
interface ChangeReport {
  lineupsPosted: number;
  hittersBecameEligible: number;
  starterChanged: number;
  nativeGenerated: number;
  aiGenerated: number;
  mlGenerated: number;
  stacksBecameReady: number;
  unchanged: string[];
}

interface SlateBoardRow {
  slateId: string;
  slateName: string | null;
  gameCount: number | null;
  playerCount: number | null;
  buildStatus: string;
  displayStatus: string;
  sourceProvenance: string | null;
  sourceHash: string | null;
  lastProcessedAt: string | null;
  lastRefreshedAt: string | null;
  publishedVersion: number | null;
  publishedAt: string | null;
  readiness: { ok: boolean; required: ReadinessCheck[]; optional: ReadinessCheck[] };
  activeJob: ActiveJob | null;
  eligibility: EligibilityCounts | null;
  identity: IdentityCounts | null;
  blueCollarCoverage: BlueCollarCoverage;
  changeReport: ChangeReport | null;
}

interface StatusResponse {
  date: string;
  providerName: string | null;
  isMock: boolean;
  slates: SlateBoardRow[];
  recentOperations: Array<{
    id: string;
    actor_label: string;
    action: string;
    target_id: string | null;
    created_at: string;
  }>;
}

interface DiscoverResponse {
  providerName: string | null;
  providerType: "mock" | "real" | null;
  isMock: boolean;
  providerStatus: string;
  providerReason: string | null;
  slatesDiscovered: Array<{ slateId: string; slateName: string | null; gameCount: number | null; playerCount: number | null }>;
  jobs: Array<{ slateId: string; slateName: string | null; jobId: string | null; action: string }>;
}

const STATUS_TONE: Record<string, string> = {
  DRAFT: "bg-text-faint/15 text-text-faint",
  PROCESSING: "bg-accent/15 text-accent",
  READY: "bg-green/15 text-green",
  PUBLISHED: "bg-green text-white",
  PARTIAL: "bg-yellow/15 text-yellow",
  ERROR: "bg-red/15 text-red",
  ARCHIVED: "bg-text-faint/15 text-text-faint",
};

function fmt(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "--" : d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function fmtOp(action: string): string {
  return action.replace(/^slate_/, "").replace(/_/g, " ");
}

/** Milestone 29: the admin Slate Operations board -- per-slate status,
 * every admin action (Process/Refresh/Publish/Unpublish/Archive), and
 * recent-operations history. Server-side auth is enforced by
 * app/admin/layout.tsx + every /api/admin/slates/* route's own
 * requireAdminApi() call -- this component is purely the UI, never the
 * security boundary. */
export function AdminSlateOperations({ date }: { date: string }) {
  const [data, setData] = useState<StatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [discoverResult, setDiscoverResult] = useState<DiscoverResponse | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`/api/admin/slates/status?date=${encodeURIComponent(date)}`);
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? "Failed to load slate status.");
        return;
      }
      setError(null);
      setData(body);
    } catch {
      setError("Failed to load slate status -- is the dashboard server running?");
    }
  }, [date]);

  useEffect(() => {
    Promise.resolve().then(refresh);
  }, [refresh]);

  // Milestone 30: while any slate has an active (QUEUED/RUNNING) job,
  // poll status every 2s so the progress bar/current step below updates
  // live without the admin needing to trigger another action -- backed
  // by lib/jobs/queue.ts's durable job rows, not this component's memory.
  const hasActiveJob = data?.slates.some((s) => s.activeJob !== null) ?? false;
  useEffect(() => {
    if (!hasActiveJob) return;
    const interval = setInterval(refresh, 2000);
    return () => clearInterval(interval);
  }, [hasActiveJob, refresh]);

  // Milestone 33.2.1 hotfix: the ONE-CLICK bulk counterpart to the
  // per-slate Process/Refresh buttons below -- queries the configured DK
  // provider (permanently the DraftKings Unofficial provider; never a
  // CSV requirement) for every real Classic slate on `date`, then starts
  // the SAME existing pipeline (runSlatePipeline via the job queue) for
  // each one discovered. Never fabricates slates when the provider isn't
  // connected -- providerStatus/providerReason below always reflect
  // exactly what the provider returned.
  const discoverTodaysSlates = useCallback(async () => {
    setDiscovering(true);
    setError(null);
    try {
      const res = await fetch("/api/admin/slates/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? "Failed to discover today's slates.");
        return;
      }
      setDiscoverResult(body as DiscoverResponse);
      await refresh();
    } catch {
      setError("Failed to discover today's slates -- is the dashboard server running?");
    } finally {
      setDiscovering(false);
    }
  }, [date, refresh]);

  async function runAction(slateId: string, slateName: string | null, action: "process" | "refresh" | "publish" | "unpublish" | "archive") {
    setBusy(`${slateId}:${action}`);
    setError(null);
    try {
      const res = await fetch(`/api/admin/slates/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date, slateId, slateLabel: slateName }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? `Failed to ${action} ${slateId}.`);
      }
      await refresh();
    } catch {
      setError(`Failed to ${action} ${slateId} -- is the dashboard server running?`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-text-muted">Slates</h2>
        <div className="flex gap-2">
          <PrimaryButton type="button" disabled={discovering || busy !== null} onClick={discoverTodaysSlates}>
            {discovering ? "Discovering..." : "Refresh Today's Slates"}
          </PrimaryButton>
          <SecondaryButton type="button" onClick={() => setShowUpload((v) => !v)}>
            {showUpload ? "Hide Upload" : "Upload DK Salary CSV"}
          </SecondaryButton>
        </div>
      </div>

      <div className="text-[11px] text-text-faint">
        DK Provider: <span className="font-medium text-text">{data?.providerName ?? "unknown"}</span>
        {data?.isMock && <span className="ml-1 font-semibold text-yellow">MOCK</span>}
      </div>

      {discoverResult && (
        <div
          className={`rounded border px-3 py-2 text-xs ${
            discoverResult.providerStatus === "ready" ? "border-green/30 bg-green/10 text-green" : "border-yellow/30 bg-yellow/10 text-yellow"
          }`}
        >
          {discoverResult.providerStatus === "ready" ? (
            <>
              Discovered {discoverResult.slatesDiscovered.length} slate{discoverResult.slatesDiscovered.length === 1 ? "" : "s"} via{" "}
              {discoverResult.providerName}
              {discoverResult.slatesDiscovered.length > 0 && (
                <>: {discoverResult.slatesDiscovered.map((s) => `${s.slateName ?? s.slateId} (${s.gameCount ?? "?"} games, ${s.playerCount ?? "?"} players)`).join(", ")}</>
              )}
              . {discoverResult.jobs.filter((j) => j.jobId).length} refresh job{discoverResult.jobs.filter((j) => j.jobId).length === 1 ? "" : "s"} started.
            </>
          ) : (
            <>DK provider not ready ({discoverResult.providerStatus}): {discoverResult.providerReason ?? "no reason given"}.</>
          )}
        </div>
      )}

      {showUpload && (
        <DraftKingsMultiCsvUpload
          date={date}
          onUploaded={() => {
            setShowUpload(false);
            refresh();
          }}
        />
      )}

      {error && <div className="rounded border border-red bg-bg-panel-raised px-3 py-2 text-xs text-red">{error}</div>}

      {!data ? (
        <p className="text-xs text-text-faint">Loading slate status...</p>
      ) : data.slates.length === 0 ? (
        <p className="text-xs text-text-faint">
          No slates discovered yet for {date} -- click &quot;Refresh Today&apos;s Slates&quot; above to query the DK provider, or upload a
          DraftKings CSV as a manual override.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {data.slates.map((s) => {
            const isPublished = s.displayStatus === "PUBLISHED";
            const isProcessing = s.buildStatus === "PROCESSING";
            return (
              <div key={s.slateId} className="rounded-[var(--radius-card)] border border-border-subtle bg-bg-panel-raised p-4">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-sm font-semibold text-text">{(s.slateName ?? s.slateId).toUpperCase()}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${STATUS_TONE[s.displayStatus] ?? STATUS_TONE.DRAFT}`}>
                    {s.displayStatus}
                    {isProcessing && s.displayStatus !== "PROCESSING" ? " (refreshing)" : ""}
                  </span>
                </div>

                {s.activeJob && (
                  <div className="mb-3">
                    <div className="mb-1 flex items-center justify-between text-[10px] text-text-faint">
                      <span>{s.activeJob.currentStep ?? (s.activeJob.status === "QUEUED" ? "Queued" : "Working...")}</span>
                      <span>{s.activeJob.progress}%</span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg-panel">
                      <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${s.activeJob.progress}%` }} />
                    </div>
                  </div>
                )}

                <dl className="mb-3 grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
                  <dt className="text-text-faint">DK Source</dt>
                  <dd className="text-text">{s.sourceProvenance ?? "--"}</dd>
                  <dt className="text-text-faint">Players</dt>
                  <dd className="text-text">{s.playerCount ?? "--"}</dd>
                  <dt className="text-text-faint">Games</dt>
                  <dd className="text-text">{s.gameCount ?? "--"}</dd>
                  <dt className="text-text-faint">Last Processed</dt>
                  <dd className="text-text">{fmt(s.lastProcessedAt)}</dd>
                  <dt className="text-text-faint">Last Refreshed</dt>
                  <dd className="text-text">{fmt(s.lastRefreshedAt)}</dd>
                  <dt className="text-text-faint">Published</dt>
                  <dd className="text-text">{isPublished ? `v${s.publishedVersion} · ${fmt(s.publishedAt)}` : "No"}</dd>
                </dl>

                {!s.activeJob && s.changeReport && (() => {
                  const r = s.changeReport;
                  const lines: string[] = [];
                  if (r.lineupsPosted > 0) lines.push(`${r.lineupsPosted} lineup${r.lineupsPosted === 1 ? "" : "s"} posted`);
                  if (r.hittersBecameEligible > 0) lines.push(`${r.hittersBecameEligible} hitter${r.hittersBecameEligible === 1 ? "" : "s"} became eligible`);
                  if (r.starterChanged > 0) lines.push(`${r.starterChanged} starter${r.starterChanged === 1 ? "" : "s"} changed`);
                  if (r.nativeGenerated > 0) lines.push(`${r.nativeGenerated} Native projection${r.nativeGenerated === 1 ? "" : "s"} generated`);
                  if (r.aiGenerated > 0) lines.push(`${r.aiGenerated} AI projection${r.aiGenerated === 1 ? "" : "s"} generated`);
                  if (r.mlGenerated > 0) lines.push(`${r.mlGenerated} ML projection${r.mlGenerated === 1 ? "" : "s"} generated`);
                  if (r.stacksBecameReady > 0) lines.push(`${r.stacksBecameReady} stack${r.stacksBecameReady === 1 ? "" : "s"} became READY`);
                  return (
                    <div className="mb-3 rounded border border-border-subtle bg-bg-panel-raised px-2 py-1.5 text-[11px]">
                      <div className="mb-1 font-semibold uppercase tracking-wide text-text-muted">Last Refresh Changes</div>
                      {lines.length === 0 ? (
                        <div className="text-text-faint">No change from the last refresh.</div>
                      ) : (
                        <ul className="list-inside list-disc text-text">
                          {lines.map((l) => (
                            <li key={l}>{l}</li>
                          ))}
                        </ul>
                      )}
                      {r.unchanged.length > 0 && (
                        <div className="mt-1 text-text-faint">No Change: {r.unchanged.join(", ")}</div>
                      )}
                    </div>
                  );
                })()}

                <div className="mb-3 flex flex-wrap gap-1.5">
                  {s.readiness.required.map((c) => (
                    <span
                      key={c.key}
                      title={c.detail}
                      className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${c.ok ? "bg-green/15 text-green" : "bg-red/15 text-red"}`}
                    >
                      {c.label}
                    </span>
                  ))}
                  {s.readiness.optional.map((c) => (
                    <span
                      key={c.key}
                      title={c.detail}
                      className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${c.ok ? "bg-green/15 text-green" : "bg-text-faint/15 text-text-faint"}`}
                    >
                      {c.label} {c.ok ? "" : "(missing)"}
                    </span>
                  ))}
                </div>

                {(() => {
                  const lineupCheck = s.readiness.required.find((c) => c.key === "lineup_confirmation");
                  return lineupCheck && !lineupCheck.ok && lineupCheck.detail.startsWith("AWAITING LINEUPS") ? (
                    <div className="mb-3 rounded border border-yellow/30 bg-yellow/10 px-2 py-1.5 text-[11px] font-medium text-yellow">
                      {lineupCheck.detail} -- re-pullable via Refresh Data, not publishable yet.
                    </div>
                  ) : null;
                })()}

                {s.identity && (
                  <div className="mb-3 border-t border-border-subtle pt-2">
                    <div className="mb-1 text-[10px] uppercase tracking-wide text-text-faint">Player Identity</div>
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px] sm:grid-cols-4">
                      <dt className="text-text-faint">Resolved</dt>
                      <dd className="text-text">{s.identity.resolved} / {s.identity.dk_entries}</dd>
                      <dt className="text-text-faint">Ambiguous</dt>
                      <dd className="text-text">{s.identity.ambiguous}</dd>
                      <dt className="text-text-faint">Unmatched</dt>
                      <dd className="text-text">{s.identity.unmatched}</dd>
                    </dl>
                  </div>
                )}

                {s.eligibility && (
                  <div className="mb-3 border-t border-border-subtle pt-2">
                    <div className="mb-1 text-[10px] uppercase tracking-wide text-text-faint">Player Pool Eligibility (Milestone 30.1)</div>
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px] sm:grid-cols-4">
                      <dt className="text-text-faint">Raw DK Players</dt>
                      <dd className="text-text">{s.eligibility.raw_dk_players}</dd>
                      <dt className="text-text-faint">Starting Pitchers</dt>
                      <dd className="text-text">{s.eligibility.starting_pitchers}</dd>
                      <dt className="text-text-faint">Confirmed Hitters</dt>
                      <dd className="text-text">{s.eligibility.confirmed_hitters}</dd>
                      <dt className="text-text-faint">Waiting For Lineups</dt>
                      <dd className="text-text">{s.eligibility.waiting_for_lineups}</dd>
                      <dt className="text-text-faint">Relief Pitchers</dt>
                      <dd className="text-text">{s.eligibility.relief_pitchers}</dd>
                      <dt className="text-text-faint">Bench</dt>
                      <dd className="text-text">{s.eligibility.bench_hitters}</dd>
                      <dt className="text-text-faint">Scratched</dt>
                      <dd className="text-text">{s.eligibility.scratched}</dd>
                      <dt className="font-semibold text-text-faint">Optimizer Eligible</dt>
                      <dd className="font-semibold text-green">{s.eligibility.optimizer_eligible}</dd>
                    </dl>
                  </div>
                )}

                {s.blueCollarCoverage.returned > 0 && (
                  <div className="mb-3 border-t border-border-subtle pt-2">
                    <div className="mb-1 text-[10px] uppercase tracking-wide text-text-faint">BlueCollar Coverage</div>
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px] sm:grid-cols-3">
                      <dt className="text-text-faint">Returned</dt>
                      <dd className="text-text">{s.blueCollarCoverage.returned}</dd>
                      <dt className="text-text-faint">Usable</dt>
                      <dd className="text-text">{s.blueCollarCoverage.usable}</dd>
                      <dt className="text-text-faint">Identity-Resolved</dt>
                      <dd className="text-text">{s.blueCollarCoverage.identityResolved}</dd>
                      <dt className="text-text-faint">Eligible</dt>
                      <dd className="text-text">{s.blueCollarCoverage.eligible}</dd>
                      <dt className="font-semibold text-text-faint">Optimizer-Ready</dt>
                      <dd className="font-semibold text-green">{s.blueCollarCoverage.optimizerReady}</dd>
                    </dl>
                  </div>
                )}

                <div className="flex flex-wrap gap-2">
                  <SecondaryButton type="button" disabled={busy !== null} onClick={() => runAction(s.slateId, s.slateName, "process")}>
                    {busy === `${s.slateId}:process` ? "Processing..." : "Process Slate"}
                  </SecondaryButton>
                  <SecondaryButton type="button" disabled={busy !== null} onClick={() => runAction(s.slateId, s.slateName, "refresh")}>
                    {busy === `${s.slateId}:refresh` ? "Refreshing..." : "Refresh Data"}
                  </SecondaryButton>
                  {isPublished ? (
                    <SecondaryButton type="button" disabled={busy !== null} onClick={() => runAction(s.slateId, s.slateName, "unpublish")}>
                      Unpublish
                    </SecondaryButton>
                  ) : (
                    <PrimaryButton
                      type="button"
                      disabled={busy !== null || !s.readiness.ok}
                      title={s.readiness.ok ? undefined : "Not ready -- see required checks above"}
                      onClick={() => runAction(s.slateId, s.slateName, "publish")}
                    >
                      Publish
                    </PrimaryButton>
                  )}
                  <SecondaryButton type="button" disabled={busy !== null} onClick={() => runAction(s.slateId, s.slateName, "archive")}>
                    Archive
                  </SecondaryButton>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel shadow-[var(--shadow-card)]">
        <div className="border-b border-border-subtle px-4 py-2 text-xs font-semibold uppercase tracking-wide text-text-faint">
          Recent Operations
        </div>
        {!data || data.recentOperations.length === 0 ? (
          <p className="p-4 text-xs text-text-faint">No admin slate operations yet today.</p>
        ) : (
          <table className="w-full text-left text-[11px]">
            <thead>
              <tr className="text-text-faint">
                <th className="px-4 py-1.5 font-medium">Time</th>
                <th className="px-4 py-1.5 font-medium">Admin</th>
                <th className="px-4 py-1.5 font-medium">Slate</th>
                <th className="px-4 py-1.5 font-medium">Operation</th>
              </tr>
            </thead>
            <tbody>
              {data.recentOperations.map((op) => (
                <tr key={op.id} className="border-t border-border-subtle">
                  <td className="px-4 py-1.5 text-text">{fmt(op.created_at)}</td>
                  <td className="px-4 py-1.5 text-text">{op.actor_label}</td>
                  <td className="px-4 py-1.5 text-text">{op.target_id ?? "--"}</td>
                  <td className="px-4 py-1.5 text-text">{fmtOp(op.action)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
