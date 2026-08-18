"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { DraftKingsMultiCsvUpload } from "@/components/DraftKingsMultiCsvUpload";
import type { SlateManagerRow } from "./types";

const STATUS_TONE: Record<SlateManagerRow["status"], string> = {
  READY: "bg-green/15 text-green",
  PARTIAL: "bg-yellow/15 text-yellow",
  MISSING: "bg-text-faint/15 text-text-faint",
};

/** Milestone 27.4 -- dfs/providers/source_provenance.py's classification,
 * mirrored here purely for display. SYNTHETIC_VALIDATION gets a loud,
 * unmissable badge -- this label must never be confused with genuine
 * real-DraftKings validation. */
const PROVENANCE_LABEL: Record<string, string> = {
  OFFICIAL_USER_UPLOAD: "Official DK Upload",
  AUTHORIZED_PROVIDER: "Authorized Provider",
  DEVELOPMENT_MOCK: "Mock",
  SYNTHETIC_VALIDATION: "TEST / SYNTHETIC DATA",
  UNKNOWN: "Unknown Source",
};

const PROVENANCE_TONE: Record<string, string> = {
  OFFICIAL_USER_UPLOAD: "bg-green/15 text-green",
  AUTHORIZED_PROVIDER: "bg-green/15 text-green",
  DEVELOPMENT_MOCK: "bg-yellow/15 text-yellow",
  SYNTHETIC_VALIDATION: "bg-red text-white animate-pulse",
  UNKNOWN: "bg-text-faint/15 text-text-faint",
};

function formatTime(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "--" : d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

interface DraftKingsUploadEntry {
  path: string;
  slate_label: string;
}

/** Milestone 26: interactive half of the Slate Manager -- the multi-CSV
 * import widget plus per-slate Open/Refresh/Remove Local Slate actions.
 * The page.tsx Server Component does the one-time slate/status read;
 * everything here that mutates state calls a real API route and then
 * router.refresh()s to re-read the authoritative server state, never
 * updating its own local copy optimistically. */
export function SlateManagerClient({
  date,
  rows,
  providerName,
  isMock,
  providerStatus,
}: {
  date: string;
  rows: SlateManagerRow[];
  providerName: string | null;
  isMock: boolean;
  providerStatus: "ready" | "not_connected" | "unavailable" | "auth_failed" | "no_slate";
}) {
  const router = useRouter();
  const [refreshingId, setRefreshingId] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const sourceLabel = isMock ? "MOCK" : providerName === "draftkings_csv" ? "DRAFTKINGS CSV" : providerName ? providerName.toUpperCase() : "NOT CONNECTED";
  const sourceTone = isMock ? "bg-yellow/15 text-yellow" : providerName ? "bg-gold/15 text-gold" : "bg-text-faint/15 text-text-faint";
  const canRemoveLocal = providerName === "draftkings_csv";

  async function handleRefresh(slateId: string) {
    setActionError(null);
    setRefreshingId(slateId);
    try {
      const res = await fetch("/api/slates/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date, slateId }),
      });
      const data = await res.json();
      if (!res.ok || data.status !== "ready") {
        setActionError(data.error ?? `Failed to refresh ${slateId}.`);
      } else {
        router.refresh();
      }
    } catch {
      setActionError(`Failed to refresh ${slateId} -- is the dashboard server running?`);
    } finally {
      setRefreshingId(null);
    }
  }

  async function handleRemove(slateId: string, slateName: string | null) {
    if (!slateName) return;
    setActionError(null);
    setRemovingId(slateId);
    try {
      const listRes = await fetch(`/api/dfs-salaries/uploads?date=${date}`);
      const listData = await listRes.json();
      const uploads = (listData.uploads as DraftKingsUploadEntry[] | undefined) ?? [];
      const match = uploads.find((u) => u.slate_label === slateName);
      if (!match) {
        setActionError(`No local upload found for ${slateName}.`);
        return;
      }
      const delRes = await fetch("/api/dfs-salaries/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: match.path }),
      });
      const delData = await delRes.json();
      if (!delRes.ok || "error" in delData) {
        setActionError(delData.error ?? `Failed to remove ${slateName}.`);
      } else {
        router.refresh();
      }
    } catch {
      setActionError(`Failed to remove ${slateName} -- is the dashboard server running?`);
    } finally {
      setRemovingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2 rounded-[var(--radius-card)] border border-border bg-bg-panel p-3 text-xs">
        <span className="text-text-faint">Source:</span>
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${sourceTone}`}>{sourceLabel}</span>
        {providerStatus === "not_connected" && (
          <span className="text-text-faint">Automatic DK salary/slate discovery is not currently available. Import a CSV below.</span>
        )}
      </div>

      <div id="import-slates">
        <DraftKingsMultiCsvUpload date={date} onUploaded={() => router.refresh()} />
      </div>

      {actionError && <div className="rounded border border-red bg-bg-panel-raised px-3 py-2 text-xs text-red">{actionError}</div>}

      <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel shadow-[var(--shadow-card)]">
        <div className="border-b border-border-subtle px-4 py-2 text-xs font-semibold uppercase tracking-wide text-text-faint">
          Today&apos;s DraftKings Slates
        </div>
        {rows.length === 0 ? (
          <p className="p-4 text-xs text-text-faint">No slates discovered yet -- import a DraftKings CSV above.</p>
        ) : (
          <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
            {rows.map((r) => (
              <div key={r.slateId} className="rounded-[var(--radius-card)] border border-border-subtle bg-bg-panel-raised p-3">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-sm font-semibold text-text">{r.slateName ?? r.slateId}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${STATUS_TONE[r.status]}`}>{r.status}</span>
                </div>
                {r.sourceProvenance && (
                  <div className="mb-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${PROVENANCE_TONE[r.sourceProvenance] ?? PROVENANCE_TONE.UNKNOWN}`}
                      title={
                        r.sourceProvenance === "SYNTHETIC_VALIDATION"
                          ? "This slate's content failed source-realism checks (e.g. an implausible pitcher count) and cannot be trusted as a genuine DraftKings export -- see the Slate Data Integrity audit."
                          : undefined
                      }
                    >
                      {PROVENANCE_LABEL[r.sourceProvenance] ?? r.sourceProvenance}
                    </span>
                  </div>
                )}
                <div className="mb-3 grid grid-cols-3 gap-2 text-center text-[11px] text-text-muted">
                  <div>
                    <div className="text-text-faint">Games</div>
                    <div className="text-text">{r.gameCount ?? "--"}</div>
                  </div>
                  <div>
                    <div className="text-text-faint">Players</div>
                    <div className="text-text">{r.playerCount ?? "--"}</div>
                  </div>
                  <div>
                    <div className="text-text-faint">Lock</div>
                    <div className="text-text">{formatTime(r.startTime)}</div>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Link
                    href={`/dashboard?slate=${encodeURIComponent(r.slateId)}`}
                    className="rounded border border-border px-2 py-1 text-[11px] text-text-muted hover:border-accent hover:text-text"
                  >
                    Open
                  </Link>
                  <button
                    type="button"
                    onClick={() => handleRefresh(r.slateId)}
                    disabled={refreshingId === r.slateId}
                    className="rounded border border-border px-2 py-1 text-[11px] text-text-muted hover:border-accent hover:text-text disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {refreshingId === r.slateId ? "Refreshing..." : "Refresh"}
                  </button>
                  {canRemoveLocal && (
                    <a
                      href="#import-slates"
                      title={`Upload a new CSV labeled "${r.slateName}" above -- it replaces this slate's data (newest upload per label always wins).`}
                      className="rounded border border-border px-2 py-1 text-[11px] text-text-muted hover:border-accent hover:text-text"
                    >
                      Replace Data
                    </a>
                  )}
                  {canRemoveLocal && (
                    <button
                      type="button"
                      onClick={() => handleRemove(r.slateId, r.slateName)}
                      disabled={removingId === r.slateId}
                      className="rounded border border-border px-2 py-1 text-[11px] text-red hover:border-red disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {removingId === r.slateId ? "Removing..." : "Remove Local Slate"}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
