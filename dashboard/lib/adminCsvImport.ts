import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import type { CanonicalSlateArtifactDocument } from "./db/canonicalArtifact";
import { promoteCanonicalArtifact } from "./db/canonicalPromotion";
import { getExecutor } from "./db/executor";
import { uploadDraftKingsCsv } from "./draftKingsUpload";
import { parseLastJsonLine } from "./optimizerWorkspace/jsonLine";
import { runPythonScript, tail } from "./orchestrator/pythonRunner";
import { getStorage } from "./storage/getStorage";

/** BREAK-GLASS ADMIN CSV UPLOAD: the TS half of the admin-CSV canonical
 * import path (see canonical_ingestion/admin_csv_import.py and
 * scripts/import_dk_csv_to_canonical.py for the Python half). Mirrors
 * dashboard/scripts/promote-canonical-slate.ts's own
 * "read a NORMALIZED artifact this process didn't write, promote it via
 * the same promoteCanonicalArtifact() every other canonical path uses"
 * pattern -- called in-process from an API route instead of a CLI, so
 * the owner never has to open a terminal (Phase 11's explicit
 * requirement).
 *
 * ADMIN CSV DATA NEVER: becomes an automatic fallback, becomes
 * customer-facing, or silently overwrites a real automatic slate -- see
 * this module's own callers (app/api/admin/slate-import/*) for where
 * those specific rules are enforced. This module is pure plumbing: CSV
 * bytes in, canonical Postgres row out (only when validationState is
 * genuinely VALID -- promoteCanonicalArtifact() itself refuses anything
 * else, see that function's own guard). */

export interface DkCsvValidationResult {
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

function writeTempCsv(bytes: Buffer): { dir: string; path: string } {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mlb-dfs-admin-csv-validate-"));
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

/** Preview-only: never persists anything (see scripts/validate_dk_csv_upload.py). */
export async function validateDkCsvUpload(csvBytes: Buffer): Promise<DkCsvValidationResult> {
  const { dir, path: csvPath } = writeTempCsv(csvBytes);
  try {
    const result = await runPythonScript("scripts/validate_dk_csv_upload.py", ["--csv-path", csvPath]);
    const doc = parseLastJsonLine(result.stdout) as Record<string, unknown> | null;
    if (!doc) {
      return { status: "invalid", reason: `Unexpected validation failure: ${tail(result.stdout + result.stderr, 500)}` };
    }
    if (doc.status !== "valid") {
      return { status: "invalid", reason: (doc.reason as string | undefined) ?? "Unknown validation failure." };
    }
    return {
      status: "valid",
      sport: doc.sport as string,
      playerCount: doc.player_count as number,
      salaryMin: doc.salary_min as number,
      salaryMax: doc.salary_max as number,
      teams: doc.teams as string[],
      positions: doc.positions as string[],
      duplicatePlayerIds: doc.duplicate_player_ids as string[],
      missingTeamCount: doc.missing_team_count as number,
      missingPositionCount: doc.missing_position_count as number,
      warnings: doc.warnings as string[],
    };
  } finally {
    cleanupTemp(dir);
  }
}

export interface AutomaticSlateCollision {
  internalSlateId: string;
  provider: string;
  providerSlateId: string;
  slateName: string | null;
  gameCount: number | null;
}

/** Phase 6: is there already a real, currently-serving AUTOMATIC (non-
 * admin-CSV) slate for this date? Used to require an explicit admin
 * choice before import rather than silently colliding with it -- the
 * canonical unique identity (sport, site, provider, providerSlateId)
 * already guarantees an admin-CSV slate can never literally overwrite
 * an automatic one (different `provider` value), but the admin should
 * still be told a real slate already exists before adding a second one
 * for the same date. */
export async function findAutomaticSlateCollision(date: string, sport: string): Promise<AutomaticSlateCollision[]> {
  const db = getExecutor();
  const rows = await db.all<{ internal_slate_id: string; provider: string; provider_slate_id: string; slate_name: string | null; game_count: number | null }>(
    "SELECT internal_slate_id, provider, provider_slate_id, slate_name, game_count FROM slates " +
      "WHERE sport = ? AND slate_date = ? AND validation_state = 'VALID' AND provider != 'draftkings_csv' ORDER BY provider_slate_id",
    [sport, date],
  );
  return rows.map((r) => ({ internalSlateId: r.internal_slate_id, provider: r.provider, providerSlateId: r.provider_slate_id, slateName: r.slate_name, gameCount: r.game_count }));
}

export interface AdminCsvImportResult {
  ok: boolean;
  reason?: string;
  internalSlateId?: string;
  providerSlateId?: string;
  slateName?: string | null;
  playerCount?: number;
  resolvedCount?: number;
  unresolvedCount?: number;
  reviewRequiredCount?: number;
  salaryMin?: number;
  salaryMax?: number;
  teams?: string[];
  positions?: string[];
  sourceProvenance?: string;
  validationState?: "PENDING" | "VALID" | "REJECTED";
  realismBlocked?: boolean;
  realismFindings?: string[];
  warnings?: string[];
}

/** Full break-glass import: (1) persist the upload via the EXISTING
 * upload path (dfs/providers/draftkings_csv_storage.py -- reused
 * unmodified, never a second storage mechanism), (2) build + write the
 * RAW/NORMALIZED canonical artifacts (Python), (3) promote to canonical
 * Postgres CURRENT (TS, promoteCanonicalArtifact -- the SAME function
 * every automatic-DK-fetch promotion uses). Never raises -- every
 * failure mode is reported in the returned result, matching this
 * project's established shadow-ingestion failure-isolation contract. */
export async function importDkCsvToCanonical(
  csvBytes: Buffer, date: string, slateLabel: string, originalFilename: string, sport = "MLB", site = "draftkings",
): Promise<AdminCsvImportResult> {
  const uploadResult = await uploadDraftKingsCsv(csvBytes, date, slateLabel, originalFilename);
  if (uploadResult.status !== "ready") {
    return { ok: false, reason: uploadResult.reason ?? "Upload failed for an unknown reason." };
  }

  const buildResult = await runPythonScript("scripts/import_dk_csv_to_canonical.py", ["--date", date, "--slate-label", slateLabel, "--sport", sport, "--site", site]);
  const doc = parseLastJsonLine(buildResult.stdout) as Record<string, unknown> | null;
  if (!doc) {
    return { ok: false, reason: `Unexpected canonical-build failure: ${tail(buildResult.stdout + buildResult.stderr, 500)}` };
  }
  if (!doc.ok) {
    return { ok: false, reason: (doc.error as string | undefined) ?? "Canonical normalization failed for an unknown reason." };
  }

  const normalizedKey = doc.normalized_key as string;
  const storage = getStorage();
  const artifact = await storage.readJson<CanonicalSlateArtifactDocument>(normalizedKey);
  if (!artifact) {
    return { ok: false, reason: `NORMALIZED artifact was written but could not be read back: ${normalizedKey}` };
  }

  const db = getExecutor();
  const promotion = await promoteCanonicalArtifact(db, artifact, { normalizedArtifactPath: normalizedKey, rawArtifactPath: (doc.raw_manifest_key as string) ?? null });

  return {
    ok: promotion.promoted,
    reason: promotion.promoted ? undefined : promotion.reason,
    internalSlateId: promotion.internalSlateId,
    providerSlateId: doc.provider_slate_id as string,
    slateName: doc.slate_name as string | null,
    playerCount: doc.player_count as number,
    resolvedCount: doc.resolved_count as number,
    unresolvedCount: doc.unresolved_count as number,
    reviewRequiredCount: doc.review_required_count as number,
    salaryMin: doc.salary_min as number,
    salaryMax: doc.salary_max as number,
    teams: doc.teams as string[],
    positions: doc.positions as string[],
    sourceProvenance: doc.source_provenance as string,
    validationState: artifact.slate.validationState,
    realismBlocked: doc.realism_blocked as boolean,
    realismFindings: doc.realism_findings as string[],
    warnings: doc.warnings as string[],
  };
}

/** Phase 9: removes an admin-CSV slate from serving without deleting
 * its history -- flips validationState to REJECTED, the SAME field
 * canonicalListSlates()/canonicalGetSlatePool() already gate serving on
 * for every other reason a slate isn't servable (e.g. a failed realism
 * check), rather than adding a parallel "active" concept. Guarded to
 * `provider = 'draftkings_csv'` so this can never touch a real
 * automatic slate, even given a wrong/forged internalSlateId. RAW/
 * NORMALIZED object-storage artifacts and the Postgres row itself are
 * never deleted -- only its servability. */
export async function deactivateAdminCsvSlate(internalSlateId: string): Promise<{ ok: boolean; reason?: string }> {
  const db = getExecutor();
  return db.transaction(async (tx) => {
    const row = await tx.get<{ validation_findings_json: string | null }>(
      "SELECT validation_findings_json FROM slates WHERE internal_slate_id = ? AND provider = 'draftkings_csv'",
      [internalSlateId],
    );
    if (!row) {
      return { ok: false, reason: "No admin-CSV slate found with that internalSlateId (or it is not a draftkings_csv slate)." };
    }
    const existingFindings: string[] = row.validation_findings_json ? JSON.parse(row.validation_findings_json) : [];
    const now = new Date().toISOString();
    const findings = [...existingFindings, `Deactivated by admin on ${now}.`];
    await tx.run(
      "UPDATE slates SET validation_state = 'REJECTED', validation_findings_json = ?, updated_at = ? WHERE internal_slate_id = ?",
      [JSON.stringify(findings), now, internalSlateId],
    );
    return { ok: true };
  });
}
