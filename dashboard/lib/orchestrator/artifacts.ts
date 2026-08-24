import { ARTIFACT_DIRS, artifactPath } from "../artifactRoot";
import { findLatestFile, safeStat } from "../discovery";

/** A cheap before/after signal that a Python step actually produced (or
 * updated) an artifact -- used because several pipeline scripts print a
 * success-looking report and still exit 0 even when they didn't save
 * anything new (e.g. an optimizer objective that finds zero legal
 * lineups). Exit code alone isn't trustworthy for those; "did the
 * relevant artifact change" is. Works for both immutable
 * timestamped-filename artifacts (path changes) and the research
 * package's fixed-name, overwritten-in-place slate.json (mtime
 * changes). */
export interface Fingerprint {
  path: string | null;
  mtimeMs: number | null;
}

export function fingerprintFixed(filePath: string): Fingerprint {
  const stat = safeStat(filePath);
  return { path: stat ? filePath : null, mtimeMs: stat ? stat.mtimeMs : null };
}

export async function fingerprintLatest(dir: string, prefix: string, ext = ".json"): Promise<Fingerprint> {
  const filePath = await findLatestFile(dir, prefix, ext);
  if (!filePath) return { path: null, mtimeMs: null };
  const stat = safeStat(filePath);
  return { path: filePath, mtimeMs: stat ? stat.mtimeMs : null };
}

export function fingerprintChanged(before: Fingerprint, after: Fingerprint): boolean {
  if (after.path === null) return false;
  if (before.path !== after.path) return true;
  if (before.mtimeMs !== null && after.mtimeMs !== null && after.mtimeMs > before.mtimeMs) return true;
  return false;
}

export function researchSlateFingerprint(date: string): Fingerprint {
  return fingerprintFixed(artifactPath(ARTIFACT_DIRS.research, date, "slate.json"));
}

export async function pitcherSnapshotFingerprint(date: string): Promise<Fingerprint> {
  return fingerprintLatest(artifactPath(ARTIFACT_DIRS.predictions, date), "pitcher_board_");
}

export async function batterSnapshotFingerprint(date: string): Promise<Fingerprint> {
  return fingerprintLatest(artifactPath(ARTIFACT_DIRS.predictions, date), "batter_board_");
}

export async function providerSlateFingerprint(date: string): Promise<Fingerprint> {
  return fingerprintLatest(artifactPath(ARTIFACT_DIRS.dfsInput, date), "provider_slate_");
}

export async function poolFingerprint(date: string): Promise<Fingerprint> {
  return fingerprintLatest(artifactPath(ARTIFACT_DIRS.dfsInput, date), "dk_player_pool_");
}

export async function matchReportFingerprint(date: string): Promise<Fingerprint> {
  return fingerprintLatest(artifactPath(ARTIFACT_DIRS.dfsInput, date), "dk_match_report_");
}

/** Milestone 26: pass `slateId` to check the slate-scoped
 * ownership_predictions/<date>/<slateId>/ directory ownership/
 * persistence.py now saves into per-slate -- omitting it checks the
 * legacy date-only directory (pre-Milestone-26 artifacts). */
export async function ownershipFingerprint(date: string, slateId?: string | null): Promise<Fingerprint> {
  const dir = slateId ? artifactPath(ARTIFACT_DIRS.ownershipPredictions, date, slateId) : artifactPath(ARTIFACT_DIRS.ownershipPredictions, date);
  return fingerprintLatest(dir, "ownership_");
}

export async function lineupSetFingerprint(date: string): Promise<Fingerprint> {
  return fingerprintLatest(artifactPath(ARTIFACT_DIRS.lineups, date), "dk_lineups_");
}
