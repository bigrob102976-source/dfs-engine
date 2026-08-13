import fs from "node:fs";
import path from "node:path";

/** Directory entries, sorted ascending by name (timestamps embedded in
 * filenames -- YYYYMMDDTHHMMSS -- sort correctly lexically, the same
 * convention the Python side already relies on in
 * research/prediction_snapshot.py's list_snapshots()). Returns [] for a
 * missing directory rather than throwing -- artifacts not existing yet
 * is an expected, common state, not an error. */
export function safeListDir(dir: string): string[] {
  try {
    return fs.readdirSync(dir).sort();
  } catch {
    return [];
  }
}

export function safeStat(filePath: string): fs.Stats | null {
  try {
    return fs.statSync(filePath);
  } catch {
    return null;
  }
}

/** Slate-date subdirectories (YYYY-MM-DD) under an artifact root,
 * newest first. */
export function listSlateDates(baseDir: string): string[] {
  return safeListDir(baseDir)
    .filter((name) => /^\d{4}-\d{2}-\d{2}$/.test(name))
    .sort()
    .reverse();
}

/** Most recent slate date, or null if none exist. */
export function latestSlateDate(baseDir: string): string | null {
  const dates = listSlateDates(baseDir);
  return dates.length ? dates[0] : null;
}

/** The most recent file in `dir` whose name starts with `prefix` and
 * ends with `ext` -- filenames sort chronologically by construction
 * (timestamp is the only variable component), so the lexical max is
 * the latest file. Returns null if the directory or a matching file
 * doesn't exist -- never throws. */
export function findLatestFile(dir: string, prefix: string, ext = ".json"): string | null {
  const matches = safeListDir(dir).filter((name) => name.startsWith(prefix) && name.endsWith(ext));
  if (matches.length === 0) return null;
  return path.join(dir, matches[matches.length - 1]);
}

/** All files in `dir` whose name starts with `prefix`, oldest first. */
export function findAllFiles(dir: string, prefix: string, ext = ".json"): string[] {
  return safeListDir(dir)
    .filter((name) => name.startsWith(prefix) && name.endsWith(ext))
    .map((name) => path.join(dir, name));
}

export function safeReadJson<T = unknown>(filePath: string | null): T | null {
  if (!filePath) return null;
  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}
