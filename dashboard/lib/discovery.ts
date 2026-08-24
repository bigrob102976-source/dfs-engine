import fs from "node:fs";
import path from "node:path";

import { getArtifactRoot, toArtifactKey } from "./artifactRoot";
import { getStorage } from "./storage/getStorage";

// Milestone 33.2: every function here now routes through getStorage()
// (LocalStorageBackend or ProductionObjectStorageBackend, chosen once by
// resolveStorageBackend()) instead of calling node:fs directly. The
// external contract is UNCHANGED on purpose -- every function still
// takes and returns ABSOLUTE local-filesystem-shaped paths (built via
// lib/artifactRoot.ts's artifactPath()), converting to/from the
// artifact-root-relative object keys StorageBackend expects internally
// via toArtifactKey(). This is the smallest migration that preserves
// existing semantics for the ~13 files that already call these
// functions with artifactPath()-built paths: none of them need to
// become object-storage-aware, they only need `await` added (see
// lib/loaders.ts and its own callers). All functions are now async --
// this is the one real breaking change, propagated everywhere they're
// called.

/** Directory entries, sorted ascending by name (timestamps embedded in
 * filenames -- YYYYMMDDTHHMMSS -- sort correctly lexically, the same
 * convention the Python side already relies on in
 * research/prediction_snapshot.py's list_snapshots()). Returns [] for a
 * missing directory rather than throwing -- artifacts not existing yet
 * is an expected, common state, not an error. */
export async function safeListDir(dir: string): Promise<string[]> {
  const key = toArtifactKey(dir);
  const files = await getStorage().listFiles(key, "", "");
  const names = files.map((f) => f.split("/").pop() as string);
  const dirs = await getStorage().listSubdirectories(key);
  return Array.from(new Set([...names, ...dirs])).sort();
}

/** Local-disk-only stat lookup (mtime/size) -- used exclusively by admin
 * diagnostics that inspect the LOCAL filesystem itself (e.g. local cache
 * inspection), never by a member-facing read path. Not routed through
 * StorageBackend: "file metadata" has no portable S3 equivalent worth
 * building for a diagnostic-only caller. Returns null when running
 * against object storage or when the path doesn't exist locally. */
export function safeStat(filePath: string): fs.Stats | null {
  try {
    return fs.statSync(filePath);
  } catch {
    return null;
  }
}

/** Slate-date subdirectories (YYYY-MM-DD) under an artifact root,
 * newest first. */
export async function listSlateDates(baseDir: string): Promise<string[]> {
  const key = toArtifactKey(baseDir);
  const dirs = await getStorage().listSubdirectories(key);
  return dirs
    .filter((name) => /^\d{4}-\d{2}-\d{2}$/.test(name))
    .sort()
    .reverse();
}

/** Most recent slate date, or null if none exist. */
export async function latestSlateDate(baseDir: string): Promise<string | null> {
  const dates = await listSlateDates(baseDir);
  return dates.length ? dates[0] : null;
}

/** The most recent file in `dir` whose name starts with `prefix` and
 * ends with `ext` -- filenames sort chronologically by construction
 * (timestamp is the only variable component), so the lexical max is
 * the latest file. Returns null if the directory or a matching file
 * doesn't exist -- never throws. Returned as an ABSOLUTE path, matching
 * this function's pre-Milestone-33.2 contract. */
/** Converts a key returned by getStorage() back into an absolute path.
 * Usually the key is artifact-root-relative (the normal case); but
 * toArtifactKey() deliberately returns an already-ABSOLUTE string for a
 * path outside the artifact root (e.g. a test's own tmpdir -- see that
 * function's docstring), and LocalStorageBackend echoes that
 * absoluteness straight through its own results. Re-joining an already-
 * absolute key onto the artifact root would silently produce a garbage
 * nested path (path.join doesn't reset on an absolute later segment the
 * way Python's pathlib `/` does), so this guards for it explicitly. */
function keyToAbsolutePath(key: string): string {
  // path.normalize converts the forward-slash key form back to the
  // platform's native separator (a no-op on POSIX, backslash on
  // Windows) so callers get exactly the same absolute-path shape this
  // function always returned pre-Milestone-33.2, regardless of which
  // branch below produced it.
  return path.normalize(path.isAbsolute(key) ? key : path.join(getArtifactRoot(), key));
}

export async function findLatestFile(dir: string, prefix: string, ext = ".json"): Promise<string | null> {
  const key = await getStorage().latestFile(toArtifactKey(dir), prefix, ext);
  return key ? keyToAbsolutePath(key) : null;
}

/** All files in `dir` whose name starts with `prefix`, oldest first --
 * returned as ABSOLUTE paths, matching this function's
 * pre-Milestone-33.2 contract. */
export async function findAllFiles(dir: string, prefix: string, ext = ".json"): Promise<string[]> {
  const keys = await getStorage().listFiles(toArtifactKey(dir), prefix, ext);
  return keys.map(keyToAbsolutePath);
}

export async function safeReadJson<T = unknown>(filePath: string | null): Promise<T | null> {
  if (!filePath) return null;
  return getStorage().readJson<T>(toArtifactKey(filePath));
}
