"use client";

import { useRef, useState } from "react";

import { PrimaryButton, SecondaryButton } from "@/components/ui/Button";
import { DK_SLATE_LABELS } from "@/lib/dkSlateLabels";

/** Milestone 19: uploads the real, official DraftKings salary-export
 * CSV a user downloads from draftkings.com for one slate. This is the
 * only way real DraftKings data enters the app (see
 * dfs/providers/base.py's no-scrape rule) -- a successful upload is
 * picked up automatically the next time "Refresh Today's Slate" runs. */
export function DraftKingsCsvUpload({ date, onUploaded }: { date: string; onUploaded?: () => void }) {
  const [slateLabel, setSlateLabel] = useState<string>(DK_SLATE_LABELS[0]);
  const [customLabel, setCustomLabel] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<{ status: "ready" | "error"; player_count?: number; reason?: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const effectiveLabel = slateLabel === "Other" ? customLabel.trim() : slateLabel;

  function handleFileSelect(selected: File | null) {
    setResult(null);
    if (!selected) return;
    if (!selected.name.toLowerCase().endsWith(".csv")) {
      setFileError("Only .csv files are supported.");
      setFile(null);
      return;
    }
    setFileError(null);
    setFile(selected);
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragActive(false);
    handleFileSelect(e.dataTransfer.files?.[0] ?? null);
  }

  function handleUpload() {
    if (!file || !effectiveLabel) return;
    setUploading(true);
    setResult(null);
    const form = new FormData();
    form.append("file", file);
    form.append("date", date);
    form.append("slateLabel", effectiveLabel);

    fetch("/api/dfs-salaries/upload", { method: "POST", body: form })
      .then((res) => res.json())
      .then((data) => {
        setUploading(false);
        setResult(data);
        if (data.status === "ready") {
          setFile(null);
          if (fileInputRef.current) fileInputRef.current.value = "";
          onUploaded?.();
        }
      })
      .catch(() => {
        setUploading(false);
        setResult({ status: "error", reason: "Upload request failed." });
      });
  }

  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-text-muted">Upload DraftKings CSV</h3>
      <p className="mb-3 text-[11px] text-text-faint">
        Download today&apos;s salary export from draftkings.com and upload it here -- real DraftKings salaries, never scraped.
      </p>

      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-xs text-text-muted">
          Slate
          <select
            value={slateLabel}
            onChange={(e) => setSlateLabel(e.target.value)}
            className="rounded border border-border bg-bg-panel-raised px-2 py-1.5 text-text"
          >
            {DK_SLATE_LABELS.map((label) => (
              <option key={label} value={label}>
                {label}
              </option>
            ))}
            <option value="Other">Other...</option>
          </select>
        </label>
        {slateLabel === "Other" && (
          <input
            type="text"
            value={customLabel}
            onChange={(e) => setCustomLabel(e.target.value)}
            placeholder="Slate name"
            className="rounded border border-border bg-bg-panel-raised px-2 py-1.5 text-xs text-text"
          />
        )}
      </div>

      <div
        className={`mt-3 flex flex-col items-center justify-center gap-2 rounded-[var(--radius-control)] border-2 border-dashed px-6 py-6 text-center transition-colors duration-150 ${
          dragActive ? "border-accent bg-accent-dim" : "border-border bg-bg-panel-raised"
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
      >
        {file ? (
          <div className="text-sm text-text">
            {file.name} <span className="text-text-faint">({Math.round(file.size / 1024)} KB)</span>
          </div>
        ) : (
          <div className="text-sm text-text-muted">Drag &amp; drop DKSalaries.csv here</div>
        )}
        <SecondaryButton type="button" onClick={() => fileInputRef.current?.click()}>
          Browse File
        </SecondaryButton>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          onChange={(e) => handleFileSelect(e.target.files?.[0] ?? null)}
        />
        {fileError && <div className="text-xs text-red">{fileError}</div>}
      </div>

      <div className="mt-3 flex items-center gap-3">
        <PrimaryButton onClick={handleUpload} disabled={!file || !effectiveLabel || uploading}>
          {uploading ? "Uploading..." : "Upload"}
        </PrimaryButton>
        {result?.status === "ready" && (
          <span className="text-xs text-green">Uploaded -- {result.player_count} players. Ready for the next refresh.</span>
        )}
        {result?.status === "error" && <span className="text-xs text-red">{result.reason}</span>}
      </div>
    </div>
  );
}
