"use client";

import { useRef, useState } from "react";

import { PrimaryButton, SecondaryButton } from "@/components/ui/Button";
import { DK_SLATE_LABELS } from "@/lib/dkSlateLabels";

interface PendingFile {
  id: string;
  file: File;
  label: string;
}

interface FileResult {
  id: string;
  filename: string;
  label: string;
  status: "ready" | "error";
  playerCount?: number;
  reason?: string;
}

/** Milestone 26: select or drag SEVERAL official DraftKings salary
 * exports at once (e.g. DK Main.csv, DK Turbo.csv, DK Night.csv) and
 * import all of them in ONE operation -- each becomes its own slate.
 * DraftKings' CSV export has no field naming the slate (see
 * dfs/providers/draftkings_csv_provider.py's docstring), so this
 * guesses a label from each filename (Main/Turbo/Night/Late/Afternoon/
 * Showdown) and lets the user correct it before importing -- it never
 * guesses slate MEMBERSHIP (which games belong to which slate), only
 * the display label, which the user can always fix. Reuses the exact
 * same single-file /api/dfs-salaries/upload route as
 * DraftKingsCsvUpload.tsx, one request per file, so nothing about how
 * an upload is validated/stored changes -- only the number of files a
 * user can queue in one sitting. */
function guessLabelFromFilename(filename: string): string {
  const stem = filename.replace(/\.csv$/i, "");
  for (const label of DK_SLATE_LABELS) {
    if (stem.toLowerCase().includes(label.toLowerCase())) return label;
  }
  return stem || "Main";
}

export function DraftKingsMultiCsvUpload({ date, onUploaded }: { date: string; onUploaded?: () => void }) {
  const [pending, setPending] = useState<PendingFile[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<FileResult[] | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function addFiles(files: FileList | File[] | null) {
    if (!files) return;
    setResults(null);
    const csvFiles = Array.from(files).filter((f) => f.name.toLowerCase().endsWith(".csv"));
    const additions: PendingFile[] = csvFiles.map((file, i) => ({
      id: `${Date.now()}-${i}-${file.name}`,
      file,
      label: guessLabelFromFilename(file.name),
    }));
    setPending((prev) => [...prev, ...additions]);
  }

  function updateLabel(id: string, label: string) {
    setPending((prev) => prev.map((p) => (p.id === id ? { ...p, label } : p)));
  }

  function removeFile(id: string) {
    setPending((prev) => prev.filter((p) => p.id !== id));
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragActive(false);
    addFiles(e.dataTransfer.files);
  }

  async function handleImportAll() {
    if (pending.length === 0) return;
    setUploading(true);
    setResults(null);
    const outcomes: FileResult[] = [];

    // Sequential, not parallel: each upload writes an immutable file +
    // sidecar (dfs/providers/draftkings_csv_storage.py) -- one at a time
    // keeps this predictable and avoids any risk of two uploads racing
    // for the same timestamp-derived filename.
    for (const item of pending) {
      const form = new FormData();
      form.append("file", item.file);
      form.append("date", date);
      form.append("slateLabel", item.label);
      try {
        const res = await fetch("/api/dfs-salaries/upload", { method: "POST", body: form });
        const data = await res.json();
        outcomes.push({
          id: item.id, filename: item.file.name, label: item.label,
          status: data.status === "ready" ? "ready" : "error",
          playerCount: data.player_count, reason: data.reason,
        });
      } catch {
        outcomes.push({ id: item.id, filename: item.file.name, label: item.label, status: "error", reason: "Upload request failed." });
      }
    }

    setResults(outcomes);
    setUploading(false);
    if (outcomes.some((o) => o.status === "ready")) {
      setPending([]);
      if (fileInputRef.current) fileInputRef.current.value = "";
      onUploaded?.();
    }
  }

  const readyCount = results?.filter((r) => r.status === "ready").length ?? 0;

  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-text-muted">Import DraftKings Slates</h3>
      <p className="mb-3 text-[11px] text-text-faint">
        Download today&apos;s salary exports from draftkings.com (Main, Turbo, Night, ...) and import several at once -- each becomes its own slate.
      </p>

      <div
        className={`flex flex-col items-center justify-center gap-2 rounded-[var(--radius-control)] border-2 border-dashed px-6 py-6 text-center transition-colors duration-150 ${
          dragActive ? "border-accent bg-accent-dim" : "border-border bg-bg-panel-raised"
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
      >
        <div className="text-sm text-text-muted">Drag &amp; drop one or more DKSalaries.csv files here</div>
        <SecondaryButton type="button" onClick={() => fileInputRef.current?.click()}>
          Browse Files
        </SecondaryButton>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,text/csv"
          multiple
          className="hidden"
          onChange={(e) => addFiles(e.target.files)}
        />
      </div>

      {pending.length > 0 && (
        <div className="mt-3 flex flex-col gap-2">
          {pending.map((item) => (
            <div key={item.id} className="flex items-center gap-2 rounded border border-border-subtle bg-bg-panel-raised px-3 py-1.5">
              <span className="min-w-0 flex-1 truncate text-xs text-text" title={item.file.name}>
                {item.file.name}
              </span>
              <input
                type="text"
                value={item.label}
                onChange={(e) => updateLabel(item.id, e.target.value)}
                aria-label={`Slate name for ${item.file.name}`}
                className="w-32 rounded border border-border bg-bg-panel px-2 py-1 text-xs text-text"
              />
              <button
                type="button"
                onClick={() => removeFile(item.id)}
                aria-label={`Remove ${item.file.name}`}
                className="text-text-faint hover:text-red"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="mt-3 flex items-center gap-3">
        <PrimaryButton onClick={handleImportAll} disabled={pending.length === 0 || uploading}>
          {uploading ? "Importing..." : pending.length > 0 ? `Import ${pending.length} Slate${pending.length === 1 ? "" : "s"}` : "Import"}
        </PrimaryButton>
      </div>

      {results && (
        <div className="mt-3 rounded border border-border-subtle bg-bg-panel-raised p-3">
          <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-text-muted">
            {readyCount} Slate{readyCount === 1 ? "" : "s"} Loaded
          </div>
          <ul className="flex flex-col gap-1">
            {results.map((r) => (
              <li key={r.id} className="text-xs">
                {r.status === "ready" ? (
                  <span className="text-green">
                    {r.label} -- {r.playerCount} players
                  </span>
                ) : (
                  <span className="text-red">
                    {r.label} ({r.filename}) -- {r.reason}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
