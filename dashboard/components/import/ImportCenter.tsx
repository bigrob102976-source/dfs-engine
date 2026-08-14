"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { DangerButton, PrimaryButton, SecondaryButton } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { CANONICAL_FIELDS } from "@/lib/csvImportFields";
import { IMPORT_PROVIDERS } from "@/lib/csvImportProviders";
import type { ColumnMapping, ImportAnalysisResult, ImportHistoryEntry, ImportSaveResult } from "@/lib/csvImport";

function formatTimestamp(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

interface ValidationStatProps {
  label: string;
  value: number;
  tone?: "neutral" | "positive" | "negative";
}

function ValidationStat({ label, value, tone = "neutral" }: ValidationStatProps) {
  const toneClass = tone === "positive" ? "text-green" : tone === "negative" ? "text-red" : "text-text";
  return (
    <div className="rounded border border-border-subtle bg-bg-panel-raised px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-text-faint">{label}</div>
      <div className={`mt-0.5 text-lg font-semibold tabular-nums ${toneClass}`}>{value}</div>
    </div>
  );
}

/** Milestone 18: the Universal Projection Import Center. Choose a
 * provider, drop a CSV, review the auto-detected column mapping (edit it
 * by hand if needed), check the validation summary, then import -- the
 * saved file becomes an immutable External Projection baseline snapshot
 * (external_projections/persistence.py, unchanged) exactly like a live
 * provider fetch, so the Optimizer's External/Adjusted projection
 * sources pick it up automatically. Import History below lists every
 * CSV-imported snapshot for today with Delete/Download/Activate. */
export function ImportCenter({ date }: { date: string }) {
  const [provider, setProvider] = useState(IMPORT_PROVIDERS[0].key);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [manualMapping, setManualMapping] = useState<ColumnMapping>({});
  const [analysis, setAnalysis] = useState<ImportAnalysisResult | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);

  const [saving, setSaving] = useState(false);
  const [saveResult, setSaveResult] = useState<ImportSaveResult | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [history, setHistory] = useState<ImportHistoryEntry[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyBusyPath, setHistoryBusyPath] = useState<string | null>(null);
  const [confirmDeletePath, setConfirmDeletePath] = useState<string | null>(null);

  const loadHistory = useCallback(() => {
    setHistoryLoading(true);
    fetch(`/api/import/history?date=${date}`)
      .then((res) => res.json())
      .then((data) => {
        setHistoryLoading(false);
        setHistory(Array.isArray(data.imports) ? data.imports : []);
      })
      .catch(() => setHistoryLoading(false));
  }, [date]);

  useEffect(() => {
    Promise.resolve().then(loadHistory);
  }, [loadHistory]);

  const runAnalyze = useCallback(
    (targetFile: File, targetProvider: string, mapping: ColumnMapping) => {
      setAnalyzing(true);
      setAnalyzeError(null);
      const form = new FormData();
      form.append("file", targetFile);
      form.append("provider", targetProvider);
      form.append("date", date);
      if (Object.keys(mapping).length > 0) form.append("mapping", JSON.stringify(mapping));

      fetch("/api/import/analyze", { method: "POST", body: form })
        .then((res) => res.json())
        .then((data) => {
          setAnalyzing(false);
          if (data.error) {
            setAnalyzeError(data.error);
            setAnalysis(null);
            return;
          }
          setAnalysis(data as ImportAnalysisResult);
        })
        .catch(() => {
          setAnalyzing(false);
          setAnalyzeError("Failed to analyze the uploaded CSV.");
        });
    },
    [date],
  );

  function handleFileSelect(selected: File | null) {
    setSaveResult(null);
    setSaveError(null);
    if (!selected) return;
    if (!selected.name.toLowerCase().endsWith(".csv")) {
      setFileError("Only .csv files are supported.");
      setFile(null);
      setAnalysis(null);
      return;
    }
    setFileError(null);
    setFile(selected);
    setManualMapping({});
    runAnalyze(selected, provider, {});
  }

  function handleProviderChange(next: string) {
    setProvider(next);
    setSaveResult(null);
    setSaveError(null);
    if (file) {
      setManualMapping({});
      runAnalyze(file, next, {});
    }
  }

  function handleMappingChange(field: string, header: string) {
    const next = { ...manualMapping, [field]: header || null };
    setManualMapping(next);
    if (file) runAnalyze(file, provider, next);
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragActive(false);
    const dropped = e.dataTransfer.files?.[0] ?? null;
    handleFileSelect(dropped);
  }

  function handleImport() {
    if (!file) return;
    setSaving(true);
    setSaveError(null);
    setSaveResult(null);
    const form = new FormData();
    form.append("file", file);
    form.append("provider", provider);
    form.append("date", date);
    if (Object.keys(manualMapping).length > 0) form.append("mapping", JSON.stringify(manualMapping));

    fetch("/api/import/save", { method: "POST", body: form })
      .then((res) => res.json())
      .then((data: ImportSaveResult) => {
        setSaving(false);
        setSaveResult(data);
        if (data.status !== "ready") {
          setSaveError(data.reason ?? "Import failed.");
          return;
        }
        setFile(null);
        setAnalysis(null);
        setManualMapping({});
        if (fileInputRef.current) fileInputRef.current.value = "";
        loadHistory();
      })
      .catch(() => {
        setSaving(false);
        setSaveError("Import request failed.");
      });
  }

  function handleActivate(path: string) {
    setHistoryBusyPath(path);
    fetch("/api/import/activate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, date }),
    })
      .then(() => {
        setHistoryBusyPath(null);
        loadHistory();
      })
      .catch(() => setHistoryBusyPath(null));
  }

  function handleDelete(path: string) {
    setConfirmDeletePath(null);
    setHistoryBusyPath(path);
    fetch("/api/import/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    })
      .then(() => {
        setHistoryBusyPath(null);
        loadHistory();
      })
      .catch(() => setHistoryBusyPath(null));
  }

  const v = analysis?.validation;
  const headers = analysis?.headers ?? [];
  const resolvedMapping = analysis?.resolved_mapping ?? {};
  const mappedHeaders = new Set(Object.values(resolvedMapping).filter((h): h is string => Boolean(h)));

  return (
    <div className="flex flex-col gap-4">
      {/* STEP 1 + 2: PROVIDER + UPLOAD */}
      <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-text-muted">1. Choose Provider &amp; Upload CSV</h2>

        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-text-muted">
            Provider
            <select
              value={provider}
              onChange={(e) => handleProviderChange(e.target.value)}
              className="min-w-[200px] rounded border border-border bg-bg-panel-raised px-2 py-1.5 text-text"
            >
              {IMPORT_PROVIDERS.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <span className="text-[11px] text-text-faint">Slate date: {date}</span>
        </div>

        <div
          className={`mt-3 flex flex-col items-center justify-center gap-2 rounded-[var(--radius-control)] border-2 border-dashed px-6 py-8 text-center transition-colors duration-150 ${
            dragActive ? "border-accent bg-accent-dim" : "border-border bg-bg-panel-raised"
          }`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={handleDrop}
        >
          <div className="text-2xl" aria-hidden="true">
            📄
          </div>
          {file ? (
            <div className="text-sm text-text">
              {file.name} <span className="text-text-faint">({Math.round(file.size / 1024)} KB)</span>
            </div>
          ) : (
            <div className="text-sm text-text-muted">Drag &amp; drop a .csv file here</div>
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
      </div>

      {analyzeError && <div className="rounded border border-red bg-bg-panel-raised px-3 py-2 text-xs text-red">{analyzeError}</div>}

      {analyzing && !analysis && <div className="text-xs text-text-faint">Analyzing CSV...</div>}

      {analysis && (
        <>
          {analysis.parse_warnings.length > 0 && (
            <div className="rounded border border-yellow bg-bg-panel-raised px-3 py-2 text-xs text-yellow">
              {analysis.parse_warnings.join(" ")}
            </div>
          )}

          {/* STEP 3: PREVIEW */}
          <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-text-muted">
              2. Preview {analysis.preview_rows.length > 0 && <span className="normal-case text-text-faint">(first {analysis.preview_rows.length} rows)</span>}
            </h2>
            {headers.length === 0 || analysis.preview_rows.length === 0 ? (
              <div className="rounded border border-border-subtle bg-bg-panel-raised p-4 text-center text-xs text-text-faint">
                No data rows to preview.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-max text-left text-xs">
                  <thead>
                    <tr className="border-b border-border-subtle">
                      {headers.map((h) => (
                        <th
                          key={h}
                          className={`whitespace-nowrap px-2 py-1.5 font-semibold uppercase tracking-wide ${
                            mappedHeaders.has(h) ? "text-accent" : "text-text-faint"
                          }`}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-subtle">
                    {analysis.preview_rows.map((row, i) => (
                      <tr key={i}>
                        {headers.map((h) => (
                          <td key={h} className="whitespace-nowrap px-2 py-1.5 text-text-muted">
                            {row[h] ?? ""}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* STEP 4: MANUAL MAPPING */}
          <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-text-muted">3. Column Mapping</h2>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
              {CANONICAL_FIELDS.map((f) => {
                const mappedHeader = resolvedMapping[f.field] ?? "";
                const autoDetected = analysis.detected_mapping[f.field];
                return (
                  <label key={f.field} className="flex flex-col gap-1 text-xs text-text-muted">
                    <span>
                      {f.label}
                      {f.required && <span className="text-red"> *</span>}
                    </span>
                    <select
                      value={mappedHeader}
                      onChange={(e) => handleMappingChange(f.field, e.target.value)}
                      className={`rounded border px-2 py-1 text-text ${mappedHeader ? "border-border bg-bg-panel-raised" : "border-yellow/50 bg-bg-panel-raised"}`}
                    >
                      <option value="">-- not mapped --</option>
                      {headers.map((h) => (
                        <option key={h} value={h}>
                          {h}
                        </option>
                      ))}
                    </select>
                    {mappedHeader && !autoDetected && <span className="text-[10px] text-accent">Manually mapped</span>}
                  </label>
                );
              })}
            </div>
          </div>

          {/* STEP 5: VALIDATION */}
          {v && (
            <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-text-muted">4. Validation Summary</h2>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
                <ValidationStat label="Imported" value={v.players_imported} />
                <ValidationStat label="Matched" value={v.matched} tone="positive" />
                <ValidationStat label="Unmatched" value={v.unmatched} tone={v.unmatched > 0 ? "negative" : "neutral"} />
                <ValidationStat label="Needs Review" value={v.ambiguous} tone={v.ambiguous > 0 ? "negative" : "neutral"} />
                <ValidationStat label="Duplicates" value={v.duplicate_players} tone={v.duplicate_players > 0 ? "negative" : "neutral"} />
                <ValidationStat label="Missing Projection" value={v.missing_projection} tone={v.missing_projection > 0 ? "negative" : "neutral"} />
                <ValidationStat label="Missing Salary" value={v.missing_salary} tone={v.missing_salary > 0 ? "negative" : "neutral"} />
                <ValidationStat label="Missing Position" value={v.missing_position} tone={v.missing_position > 0 ? "negative" : "neutral"} />
                <ValidationStat label="Unknown Teams" value={v.unknown_teams.length} tone={v.unknown_teams.length > 0 ? "negative" : "neutral"} />
              </div>

              {v.unknown_teams.length > 0 && (
                <div className="mt-3 text-xs text-text-faint">Unknown teams: {v.unknown_teams.join(", ")}</div>
              )}

              {v.needs_review.length > 0 && (
                <div className="mt-3">
                  <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-yellow">Needs Review (ambiguous match)</div>
                  <ul className="flex flex-col gap-1 text-xs text-text-muted">
                    {v.needs_review.map((r) => (
                      <li key={r.row_index} className="rounded border border-border-subtle bg-bg-panel-raised px-2 py-1">
                        {r.name} ({r.team}) -- candidates: {r.candidate_names.join(", ") || "none"}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {(analysis.skipped_missing_name > 0 || analysis.skipped_missing_projection > 0) && (
                <div className="mt-3 text-xs text-text-faint">
                  {analysis.skipped_missing_name} row(s) skipped (no name), {analysis.skipped_missing_projection} row(s) skipped (no projection).
                  Only rows with both are imported.
                </div>
              )}
            </div>
          )}

          {/* STEP 6: IMPORT */}
          <div className="flex items-center gap-3 rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
            <PrimaryButton onClick={handleImport} disabled={saving || analyzing || analysis.importable_player_count === 0}>
              {saving ? "Importing..." : `Import ${analysis.importable_player_count} Player(s)`}
            </PrimaryButton>
            {analysis.importable_player_count === 0 && <span className="text-xs text-text-faint">No importable rows (need both a name and a projection).</span>}
          </div>
        </>
      )}

      {/* Deliberately rendered OUTSIDE the `analysis &&` block above: a
          successful import clears `analysis` (see handleImport) so the
          wizard resets for the next upload, but this confirmation must
          stay visible after that happens. */}
      {saveError && <div className="rounded border border-red bg-bg-panel-raised px-3 py-2 text-xs text-red">{saveError}</div>}

      {saveResult?.status === "ready" && (
        <div className="rounded-[var(--radius-card)] border border-green bg-bg-panel p-4 shadow-[var(--shadow-card)]">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-green">Import Successful</h2>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
            <dt className="text-text-faint">Provider</dt>
            <dd className="text-text">{saveResult.provider_name}</dd>
            <dt className="text-text-faint">Players Imported</dt>
            <dd className="text-text">{saveResult.player_count}</dd>
            <dt className="text-text-faint">Matched</dt>
            <dd className="text-text">{saveResult.validation_summary?.matched}</dd>
            <dt className="text-text-faint">Snapshot</dt>
            <dd className="truncate text-text" title={saveResult.path}>
              {saveResult.path}
            </dd>
          </dl>
          <p className="mt-2 text-[11px] text-text-faint">
            {saveResult.adjustment?.status === "ready"
              ? "Available inside the Optimizer as External / Adjusted projection sources."
              : "Saved as an immutable snapshot. The Optimizer will pick it up once pitcher/batter research exists for this date."}
          </p>
        </div>
      )}

      {/* IMPORT HISTORY */}
      <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-text-muted">Import History -- {date}</h2>
        {historyLoading ? (
          <div className="text-xs text-text-faint">Loading...</div>
        ) : history.length === 0 ? (
          <div className="rounded border border-border-subtle bg-bg-panel-raised p-4 text-center text-xs text-text-faint">
            No CSV imports for this date yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-max text-left text-xs">
              <thead>
                <tr className="border-b border-border-subtle text-text-faint">
                  <th className="px-2 py-1.5 font-semibold uppercase tracking-wide">Provider</th>
                  <th className="px-2 py-1.5 font-semibold uppercase tracking-wide">Imported</th>
                  <th className="px-2 py-1.5 font-semibold uppercase tracking-wide">Players</th>
                  <th className="px-2 py-1.5 font-semibold uppercase tracking-wide">Matched</th>
                  <th className="px-2 py-1.5 font-semibold uppercase tracking-wide">Unmatched</th>
                  <th className="px-2 py-1.5 font-semibold uppercase tracking-wide">Status</th>
                  <th className="px-2 py-1.5 font-semibold uppercase tracking-wide">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {history.map((entry) => {
                  const busy = historyBusyPath === entry.path;
                  return (
                    <tr key={entry.path}>
                      <td className="px-2 py-1.5 text-text">{entry.provider_name}</td>
                      <td className="px-2 py-1.5 text-text-muted">{formatTimestamp(entry.retrieved_at)}</td>
                      <td className="px-2 py-1.5 text-text-muted">{entry.player_count}</td>
                      <td className="px-2 py-1.5 text-text-muted">{entry.matched ?? "--"}</td>
                      <td className="px-2 py-1.5 text-text-muted">{entry.unmatched ?? "--"}</td>
                      <td className="px-2 py-1.5">
                        {entry.is_active ? (
                          <span className="rounded-full bg-green/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-green">Active</span>
                        ) : (
                          <span className="rounded-full bg-bg-panel-raised px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-text-faint">Inactive</span>
                        )}
                      </td>
                      <td className="px-2 py-1.5">
                        <div className="flex items-center gap-1.5">
                          {!entry.is_active && (
                            <SecondaryButton type="button" disabled={busy} onClick={() => handleActivate(entry.path)}>
                              Activate
                            </SecondaryButton>
                          )}
                          <a href={`/api/import/download?path=${encodeURIComponent(entry.path)}`} className="rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-3.5 py-2 text-xs font-semibold text-text-muted transition-colors duration-150 hover:border-accent hover:text-text">
                            Download
                          </a>
                          <DangerButton type="button" disabled={busy} onClick={() => setConfirmDeletePath(entry.path)}>
                            Delete
                          </DangerButton>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {confirmDeletePath && (
        <Modal onClose={() => setConfirmDeletePath(null)} ariaLabel="Confirm delete import">
          <h2 className="mb-2 text-sm font-semibold text-text">Delete this import?</h2>
          <p className="mb-4 text-xs text-text-faint">This permanently removes the CSV-imported snapshot file. This cannot be undone.</p>
          <div className="flex justify-end gap-2">
            <SecondaryButton type="button" onClick={() => setConfirmDeletePath(null)}>
              Cancel
            </SecondaryButton>
            <DangerButton type="button" onClick={() => handleDelete(confirmDeletePath)}>
              Delete
            </DangerButton>
          </div>
        </Modal>
      )}
    </div>
  );
}
