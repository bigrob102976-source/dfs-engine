"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { PrimaryButton, SecondaryButton } from "@/components/ui/Button";
import { DK_SLATE_LABELS } from "@/lib/dkSlateLabels";

interface ValidationResult {
  status: "valid" | "invalid";
  reason?: string;
  sport?: string;
  playerCount?: number;
  salaryMin?: number;
  salaryMax?: number;
  teams?: string[];
  positions?: string[];
  duplicatePlayerIds?: string[];
  missingTeamCount?: number;
  missingPositionCount?: number;
  warnings?: string[];
}

interface Collision {
  internalSlateId: string;
  provider: string;
  providerSlateId: string;
  slateName: string | null;
  gameCount: number | null;
}

interface ImportResult {
  ok: boolean;
  reason?: string;
  requiresConfirmation?: boolean;
  collisions?: Collision[];
  internalSlateId?: string;
  providerSlateId?: string;
  slateName?: string | null;
  playerCount?: number;
  salaryMin?: number;
  salaryMax?: number;
  teams?: string[];
  sourceProvenance?: string;
  validationState?: "PENDING" | "VALID" | "REJECTED";
  realismBlocked?: boolean;
  realismFindings?: string[];
  warnings?: string[];
  downstreamRefreshJobId?: string;
}

/** BREAK-GLASS ADMIN CSV UPLOAD, Phase 2/6/9/11: Choose File -> Validate
 * -> preview -> Import Slate. Never imports automatically on file
 * selection (Phase 2's explicit rule) -- Validate and Import are always
 * two distinct, deliberate clicks against two distinct server-side-
 * gated routes (app/api/admin/slate-import/{validate,import}). */
export function SlateImportPanel({ defaultDate }: { defaultDate: string }) {
  const [date, setDate] = useState(defaultDate);
  const [slateLabel, setSlateLabel] = useState("Main");
  const [file, setFile] = useState<File | null>(null);
  const [validating, setValidating] = useState(false);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [deactivating, setDeactivating] = useState(false);
  const [deactivated, setDeactivated] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function resetForNewFile(f: File | null) {
    setFile(f);
    setValidation(null);
    setImportResult(null);
    setDeactivated(false);
  }

  async function handleValidate() {
    if (!file) return;
    setValidating(true);
    setValidation(null);
    setImportResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/admin/slate-import/validate", { method: "POST", body: form });
      const data = (await res.json()) as ValidationResult;
      setValidation(data);
    } catch {
      setValidation({ status: "invalid", reason: "Validation request failed." });
    } finally {
      setValidating(false);
    }
  }

  async function handleImport(confirmSeparateSlate: boolean) {
    if (!file) return;
    setImporting(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("date", date);
      form.append("slateLabel", slateLabel);
      if (confirmSeparateSlate) form.append("confirmSeparateSlate", "true");
      const res = await fetch("/api/admin/slate-import/import", { method: "POST", body: form });
      const data = (await res.json()) as ImportResult;
      setImportResult(data);
    } catch {
      setImportResult({ ok: false, reason: "Import request failed." });
    } finally {
      setImporting(false);
    }
  }

  async function handleDeactivate() {
    if (!importResult?.internalSlateId) return;
    setDeactivating(true);
    try {
      const res = await fetch("/api/admin/slate-import/deactivate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ internalSlateId: importResult.internalSlateId }),
      });
      const data = (await res.json()) as { ok: boolean; reason?: string };
      if (data.ok) setDeactivated(true);
    } finally {
      setDeactivating(false);
    }
  }

  const canValidate = !!file && !validating;
  const canImport = !!file && validation?.status === "valid" && !importing;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs text-text-muted">
          Slate date
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="rounded border border-border bg-bg-panel-raised px-2 py-1 text-sm text-text"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-text-muted">
          Slate label
          <input
            type="text"
            list="slate-import-label-suggestions"
            value={slateLabel}
            onChange={(e) => setSlateLabel(e.target.value)}
            className="w-40 rounded border border-border bg-bg-panel-raised px-2 py-1 text-sm text-text"
          />
          <datalist id="slate-import-label-suggestions">
            {DK_SLATE_LABELS.map((l) => (
              <option key={l} value={l} />
            ))}
          </datalist>
        </label>
      </div>

      <div className="flex items-center gap-3">
        <SecondaryButton type="button" onClick={() => fileInputRef.current?.click()}>
          Choose File
        </SecondaryButton>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          onChange={(e) => resetForNewFile(e.target.files?.[0] ?? null)}
        />
        <span className="text-xs text-text-faint">{file ? file.name : "No file selected"}</span>
      </div>

      <div className="flex items-center gap-3">
        <PrimaryButton onClick={handleValidate} disabled={!canValidate}>
          {validating ? "Validating..." : "Validate"}
        </PrimaryButton>
        {validation?.status === "valid" && (
          <PrimaryButton onClick={() => handleImport(false)} disabled={!canImport}>
            {importing ? "Importing..." : "Import Slate"}
          </PrimaryButton>
        )}
      </div>

      {validation?.status === "invalid" && (
        <div className="rounded border border-red/40 bg-red/10 p-3 text-xs text-red">Invalid CSV: {validation.reason}</div>
      )}

      {validation?.status === "valid" && (
        <div className="rounded border border-border-subtle bg-bg-panel-raised p-3 text-xs">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-muted">Preview (not yet imported)</div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3">
            <div>
              Sport: <span className="text-text">{validation.sport}</span>
            </div>
            <div>
              Players: <span className="text-text">{validation.playerCount}</span>
            </div>
            <div>
              Salary range: <span className="text-text">${validation.salaryMin?.toLocaleString()} - ${validation.salaryMax?.toLocaleString()}</span>
            </div>
            <div>
              Teams: <span className="text-text">{validation.teams?.length}</span>
            </div>
            <div>
              Positions: <span className="text-text">{validation.positions?.join(", ")}</span>
            </div>
          </div>
          {(validation.duplicatePlayerIds?.length ?? 0) > 0 && (
            <div className="mt-2 text-yellow">Duplicate DK player IDs: {validation.duplicatePlayerIds!.join(", ")}</div>
          )}
          {(validation.missingTeamCount ?? 0) > 0 && <div className="mt-1 text-yellow">{validation.missingTeamCount} row(s) missing a team.</div>}
          {(validation.missingPositionCount ?? 0) > 0 && <div className="mt-1 text-yellow">{validation.missingPositionCount} row(s) missing a position.</div>}
        </div>
      )}

      {importResult?.requiresConfirmation && (
        <div className="rounded border border-yellow/40 bg-yellow/10 p-3 text-xs">
          <div className="mb-2 font-semibold text-yellow">A live automatic slate already exists for {date}:</div>
          <ul className="mb-3 flex flex-col gap-1">
            {importResult.collisions?.map((c) => (
              <li key={c.internalSlateId} className="text-text">
                {c.slateName ?? c.providerSlateId} ({c.provider}) -- {c.gameCount ?? "?"} games
              </li>
            ))}
          </ul>
          <div className="flex gap-2">
            <SecondaryButton type="button" onClick={() => setImportResult(null)}>
              Cancel
            </SecondaryButton>
            <PrimaryButton onClick={() => handleImport(true)} disabled={importing}>
              {importing ? "Importing..." : "Import as Separate Admin CSV Slate"}
            </PrimaryButton>
          </div>
        </div>
      )}

      {importResult && !importResult.requiresConfirmation && !importResult.ok && (
        <div className="rounded border border-red/40 bg-red/10 p-3 text-xs text-red">Import failed: {importResult.reason}</div>
      )}

      {importResult?.ok && (
        <div className="rounded border border-green/40 bg-green/10 p-3 text-xs">
          <div className="mb-2 text-sm font-semibold text-green">Imported successfully</div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3">
            <div>
              Slate: <span className="text-text">{importResult.slateName ?? importResult.providerSlateId}</span>
            </div>
            <div>
              Players: <span className="text-text">{importResult.playerCount}</span>
            </div>
            <div>
              Salary range: <span className="text-text">${importResult.salaryMin?.toLocaleString()} - ${importResult.salaryMax?.toLocaleString()}</span>
            </div>
            <div>
              Teams: <span className="text-text">{importResult.teams?.length}</span>
            </div>
            <div>
              Status: <span className="text-text">{importResult.validationState}</span>
            </div>
          </div>
          {importResult.realismBlocked && (
            <div className="mt-2 text-red">
              This slate FAILED content-realism checks and was rejected -- it will not appear in the optimizer. See findings below.
            </div>
          )}
          {(importResult.realismFindings?.length ?? 0) > 0 && (
            <ul className="mt-1 list-disc pl-4 text-text-faint">
              {importResult.realismFindings!.slice(0, 5).map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          )}
          <div className="mt-3 flex items-center gap-3">
            {importResult.validationState === "VALID" && !importResult.realismBlocked && (
              <Link href="/dashboard/optimizer" className="text-accent hover:text-accent-hover">
                Open MLB Optimizer →
              </Link>
            )}
            {!deactivated && importResult.internalSlateId && (
              <SecondaryButton type="button" onClick={handleDeactivate} disabled={deactivating}>
                {deactivating ? "Deactivating..." : "Deactivate This Import"}
              </SecondaryButton>
            )}
            {deactivated && <span className="text-text-faint">Deactivated -- no longer visible to the optimizer.</span>}
          </div>
          <div className="mt-2 text-text-faint">Downstream research/eligibility/projections/ownership refresh started in the background.</div>
        </div>
      )}
    </div>
  );
}
