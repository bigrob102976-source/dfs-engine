"use client";

import { useRef, useState } from "react";

interface ImportResult {
  status: "ready" | "error" | "no_players";
  record_count?: number;
  matched_count?: number;
  match_rate?: number;
  contest_name?: string;
  reason?: string;
}

/** "Results → Import DK Contest Results" (Milestone 27, Part 4) -- the
 * obvious, dedicated UI location the milestone asks for. Purely
 * optional: actual DK fantasy points are already available without
 * this (see the Projection Lab's "Actual DK" column) -- this only adds
 * real actual ownership / contest score / rank / field size once the
 * user has downloaded their own contest-standings CSV from
 * draftkings.com. Never scrapes, never automates a DraftKings login. */
export function ImportContestResultsCard({ date, slateId }: { date: string; slateId: string | null }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);

  async function handleFile(file: File) {
    setBusy(true);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("date", date);
      if (slateId) form.append("slateId", slateId);
      const res = await fetch("/api/results/import-contest", { method: "POST", body: form });
      const doc = (await res.json()) as ImportResult;
      setResult(doc);
    } catch {
      setResult({ status: "error", reason: "Upload failed." });
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-text-muted">Import DK Contest Results</div>
      <p className="mb-3 text-xs text-text-faint">
        Upload a real DraftKings contest-standings CSV (downloaded from draftkings.com) for actual ownership, contest score, rank, and field size.
        Never required for Actual DK points, which come from MLB Stats results automatically.
      </p>
      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        disabled={busy}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void handleFile(file);
        }}
        className="text-xs text-text-muted file:mr-3 file:rounded file:border-0 file:bg-accent-dim file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-text"
      />
      {busy && <p className="mt-2 text-xs text-text-faint">Importing...</p>}
      {result?.status === "ready" && (
        <p className="mt-2 text-xs text-green">
          Imported {result.record_count} rows for {result.contest_name} -- {Math.round((result.match_rate ?? 0) * 100)}% matched ({result.matched_count}/{result.record_count}).
        </p>
      )}
      {result && result.status !== "ready" && <p className="mt-2 text-xs text-red">{result.reason ?? "Import failed."}</p>}
    </div>
  );
}
