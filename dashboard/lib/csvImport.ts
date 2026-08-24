import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { ARTIFACT_DIRS, artifactPath } from "./artifactRoot";
import { safeReadJson } from "./discovery";
import { parseLastJsonLine } from "./optimizerWorkspace/jsonLine";
import { runPythonScript, tail } from "./orchestrator/pythonRunner";

export type ColumnMapping = Record<string, string | null>;

export interface NeedsReviewRow {
  row_index: number;
  name: string;
  team: string;
  candidate_names: string[];
  candidate_mlb_ids: string[];
}

export interface ImportValidationSummary {
  players_imported: number;
  matched: number;
  unmatched: number;
  ambiguous: number;
  duplicate_players: number;
  missing_salary: number;
  missing_projection: number;
  missing_position: number;
  unknown_teams: string[];
  unknown_opponents: string[];
  needs_review: NeedsReviewRow[];
}

export interface ImportAnalysisResult {
  headers: string[];
  detected_mapping: ColumnMapping;
  resolved_mapping: ColumnMapping;
  preview_rows: Record<string, string>[];
  parse_warnings: string[];
  validation: ImportValidationSummary;
  importable_player_count: number;
  skipped_missing_name: number;
  skipped_missing_projection: number;
}

export interface ImportAdjustmentResult {
  status: string;
  record_count?: number;
  reason?: string;
}

export interface ImportSaveResult {
  status: "ready" | "no_players" | "error";
  path?: string;
  player_count?: number;
  provider_name?: string;
  validation_summary?: ImportValidationSummary;
  reason?: string;
  adjustment?: ImportAdjustmentResult;
}

export interface ImportHistoryEntry {
  path: string;
  slate_date: string;
  provider: string;
  provider_name: string;
  original_filename: string | null;
  retrieved_at: string;
  player_count: number;
  matched: number | null;
  unmatched: number | null;
  ambiguous: number | null;
  is_active: boolean;
}

function writeTempCsv(bytes: Buffer): { dir: string; path: string } {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mlb-dfs-csv-import-"));
  const filePath = path.join(dir, "upload.csv");
  fs.writeFileSync(filePath, bytes);
  return { dir, path: filePath };
}

function cleanupTemp(dir: string): void {
  try {
    fs.rmSync(dir, { recursive: true, force: true });
  } catch {
    // Best-effort cleanup of an OS temp file -- never fail a request over this.
  }
}

/** Analyzes an uploaded CSV without saving anything -- powers the wizard's
 * Preview/Column Mapping/Validation Summary steps. Safe to call again on
 * every mapping edit (see external_projections/csv_import/importer.py). */
export async function analyzeProjectionCsv(
  csvBytes: Buffer,
  provider: string,
  date: string,
  mapping?: ColumnMapping | null,
): Promise<ImportAnalysisResult | { error: string }> {
  const { dir, path: csvPath } = writeTempCsv(csvBytes);
  try {
    const args = ["--csv-path", csvPath, "--provider", provider, "--date", date];
    if (mapping && Object.keys(mapping).length > 0) args.push("--mapping", JSON.stringify(mapping));
    const result = await runPythonScript("scripts/analyze_projection_csv.py", args);
    const doc = parseLastJsonLine(result.stdout);
    if (!doc || result.exitCode !== 0) {
      return { error: `Unexpected CSV analysis failure: ${tail(result.stdout + result.stderr, 500)}` };
    }
    if (doc.status === "error") {
      return { error: (doc.reason as string | undefined) ?? "Failed to analyze the uploaded CSV." };
    }
    return doc as unknown as ImportAnalysisResult;
  } finally {
    cleanupTemp(dir);
  }
}

/** Saves an uploaded CSV as an immutable external-projection baseline
 * snapshot, then -- mirroring the existing provider-fetched-baseline flow
 * -- immediately runs the Big Money Research Adjustment Layer against it
 * so the Optimizer's External/Adjusted projection sources pick it up
 * (see scripts/run_projection_adjustment.py). The adjustment step is
 * best-effort: e.g. no research package existing yet for this date is a
 * normal state, not an import failure, so it's reported separately under
 * `adjustment` rather than failing the whole save. */
export async function saveProjectionCsvImport(
  csvBytes: Buffer,
  provider: string,
  date: string,
  originalFilename: string,
  mapping?: ColumnMapping | null,
): Promise<ImportSaveResult> {
  const { dir, path: csvPath } = writeTempCsv(csvBytes);
  let saveDoc: Record<string, unknown> | null;
  try {
    const args = ["--csv-path", csvPath, "--provider", provider, "--date", date, "--original-filename", originalFilename];
    if (mapping && Object.keys(mapping).length > 0) args.push("--mapping", JSON.stringify(mapping));
    const result = await runPythonScript("scripts/save_projection_csv_import.py", args);
    saveDoc = parseLastJsonLine(result.stdout);
    if (!saveDoc) {
      return { status: "error", reason: `Unexpected save failure: ${tail(result.stdout + result.stderr, 500)}` };
    }
  } finally {
    cleanupTemp(dir);
  }

  if (saveDoc.status !== "ready") {
    return saveDoc as unknown as ImportSaveResult;
  }

  const adjustResult = await runPythonScript("scripts/run_projection_adjustment.py", ["--date", date]);
  const adjustDoc = parseLastJsonLine(adjustResult.stdout);

  return {
    ...(saveDoc as unknown as ImportSaveResult),
    adjustment: adjustDoc
      ? { status: String(adjustDoc.status), record_count: adjustDoc.record_count as number | undefined, reason: adjustDoc.reason as string | undefined }
      : { status: "error", reason: "The adjustment layer did not return a result." },
  };
}

export async function listProjectionImports(date: string): Promise<ImportHistoryEntry[] | { error: string }> {
  const result = await runPythonScript("scripts/list_projection_imports.py", ["--date", date]);
  const doc = parseLastJsonLine(result.stdout);
  if (!doc || result.exitCode !== 0) {
    return { error: `Unexpected import-history failure: ${tail(result.stdout + result.stderr, 500)}` };
  }
  return (doc.imports as ImportHistoryEntry[] | undefined) ?? [];
}

export async function deleteProjectionImport(importPath: string): Promise<{ ok: true } | { error: string }> {
  const result = await runPythonScript("scripts/delete_projection_import.py", ["--path", importPath]);
  const doc = parseLastJsonLine(result.stdout);
  if (!doc || result.exitCode !== 0 || doc.status !== "ok") {
    return { error: (doc?.reason as string | undefined) ?? `Unexpected delete failure: ${tail(result.stdout + result.stderr, 500)}` };
  }
  return { ok: true };
}

/** Makes an older CSV-imported snapshot active again (a fresh, newer-
 * timestamped copy -- see external_projections/csv_import/history.py),
 * then re-runs the adjustment layer so the Optimizer picks up the
 * snapshot that is now newest. */
export async function activateProjectionImport(importPath: string, date: string): Promise<{ ok: true; path: string } | { error: string }> {
  const result = await runPythonScript("scripts/reactivate_projection_import.py", ["--path", importPath]);
  const doc = parseLastJsonLine(result.stdout);
  if (!doc || result.exitCode !== 0 || doc.status !== "ready") {
    return { error: (doc?.reason as string | undefined) ?? `Unexpected activation failure: ${tail(result.stdout + result.stderr, 500)}` };
  }
  await runPythonScript("scripts/run_projection_adjustment.py", ["--date", date]);
  return { ok: true, path: doc.path as string };
}

/** Validates that `rawPath` is a CSV-imported baseline snapshot file
 * inside external_projection_snapshots/ before it's ever opened for
 * download -- the one History action (Download) that reads the file
 * directly rather than going through a Python script that already
 * enforces this (see history.py::_validate_owned_path). Returns null for
 * anything outside the snapshot root, not named like a baseline
 * snapshot, or not tagged source == "csv_import". */
export async function resolveOwnedImportSnapshotPath(rawPath: string): Promise<string | null> {
  const root = artifactPath(ARTIFACT_DIRS.externalProjectionSnapshots);
  const resolved = path.resolve(rawPath);
  const relative = path.relative(root, resolved);
  if (relative.startsWith("..") || path.isAbsolute(relative)) return null;

  const basename = path.basename(resolved);
  if (!basename.startsWith("provider_") || !basename.endsWith(".json")) return null;

  const doc = await safeReadJson<{ source?: string }>(resolved);
  if (!doc || doc.source !== "csv_import") return null;

  return resolved;
}
