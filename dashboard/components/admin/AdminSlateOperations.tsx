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
        <SecondaryButton type="button" onClick={() => setShowUpload((v) => !v)}>
          {showUpload ? "Hide Upload" : "Upload DK Salary CSV"}
        </SecondaryButton>
      </div>

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
        <p className="text-xs text-text-faint">No slates discovered yet for {date} -- upload a DraftKings CSV above.</p>
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
