import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { parseLastJsonLine } from "./optimizerWorkspace/jsonLine";
import { runPythonScript, tail } from "./orchestrator/pythonRunner";

// Milestone 27 -- Part 4 (Results Foundation). Reuses the Milestone 11
// ingestion architecture (evaluation/actual_ownership_*.py) via
// scripts/import_dk_contest_results.py -- this module never parses a
// CSV or resolves a player itself, it only shells out and reports the
// script's own result, mirroring lib/draftKingsUpload.ts's exact
// temp-file/cleanup pattern for the (unrelated) DK salary CSV upload.

export interface ContestResultsImportResult {
  status: "ready" | "error" | "no_players";
  path?: string;
  record_count?: number;
  matched_count?: number;
  match_rate?: number;
  contest_name?: string;
  contest_id?: string;
  reason?: string;
}

function writeTempCsv(bytes: Buffer): { dir: string; path: string } {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mlb-dfs-contest-results-"));
  const filePath = path.join(dir, "contest_results.csv");
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

export async function importDkContestResults(csvBytes: Buffer, date: string, slateId: string | null): Promise<ContestResultsImportResult> {
  const { dir, path: csvPath } = writeTempCsv(csvBytes);
  try {
    const args = ["--csv-path", csvPath, "--date", date];
    if (slateId) args.push("--slate-id", slateId);
    const result = await runPythonScript("scripts/import_dk_contest_results.py", args);
    const doc = parseLastJsonLine(result.stdout);
    if (!doc) {
      return { status: "error", reason: `Unexpected import failure: ${tail(result.stdout + result.stderr, 500)}` };
    }
    return doc as unknown as ContestResultsImportResult;
  } finally {
    cleanupTemp(dir);
  }
}
