import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { parseLastJsonLine } from "./optimizerWorkspace/jsonLine";
import { runPythonScript, tail } from "./orchestrator/pythonRunner";

/** Milestone 19: uploads the real, official DraftKings salary-export
 * CSV a user downloads from draftkings.com -- never a scraped or
 * automatically-fetched file (see dfs/providers/base.py's no-scrape
 * rule and dfs/providers/draftkings_csv_provider.py). Thin wrapper
 * around the Python CLI scripts that own validation/storage. */

export interface DraftKingsUploadResult {
  status: "ready" | "error";
  path?: string;
  slate_label?: string;
  player_count?: number;
  reason?: string;
}

export interface DraftKingsUploadEntry {
  path: string;
  meta_path: string;
  slate_date: string;
  slate_label: string;
  original_filename: string;
  uploaded_at: string;
}

function writeTempCsv(bytes: Buffer): { dir: string; path: string } {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mlb-dfs-dk-upload-"));
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

export async function uploadDraftKingsCsv(
  csvBytes: Buffer, date: string, slateLabel: string, originalFilename: string,
): Promise<DraftKingsUploadResult> {
  const { dir, path: csvPath } = writeTempCsv(csvBytes);
  try {
    const args = ["--csv-path", csvPath, "--date", date, "--slate-label", slateLabel, "--original-filename", originalFilename];
    const result = await runPythonScript("scripts/upload_draftkings_csv.py", args);
    const doc = parseLastJsonLine(result.stdout);
    if (!doc) {
      return { status: "error", reason: `Unexpected upload failure: ${tail(result.stdout + result.stderr, 500)}` };
    }
    return doc as unknown as DraftKingsUploadResult;
  } finally {
    cleanupTemp(dir);
  }
}

export async function listDraftKingsUploads(date: string): Promise<DraftKingsUploadEntry[] | { error: string }> {
  const result = await runPythonScript("scripts/list_draftkings_uploads.py", ["--date", date]);
  const doc = parseLastJsonLine(result.stdout);
  if (!doc || result.exitCode !== 0) {
    return { error: `Unexpected upload-listing failure: ${tail(result.stdout + result.stderr, 500)}` };
  }
  return (doc.uploads as DraftKingsUploadEntry[] | undefined) ?? [];
}

export async function deleteDraftKingsUpload(uploadPath: string): Promise<{ ok: true } | { error: string }> {
  const result = await runPythonScript("scripts/delete_draftkings_upload.py", ["--path", uploadPath]);
  const doc = parseLastJsonLine(result.stdout);
  if (!doc || result.exitCode !== 0 || doc.status !== "ok") {
    return { error: (doc?.reason as string | undefined) ?? `Unexpected delete failure: ${tail(result.stdout + result.stderr, 500)}` };
  }
  return { ok: true };
}
