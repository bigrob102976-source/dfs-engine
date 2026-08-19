// Milestone 29 hosting-preparation audit: every artifact this dashboard
// reads (research_output/, predictions/, dfs_input/, native/AI/ownership/
// game-environment snapshots -- the full list is
// dashboard/lib/artifactRoot.ts::ARTIFACT_DIRS) currently lives ONLY on
// local disk, read via plain node:fs calls (lib/discovery.ts) relative
// to getArtifactRoot(). That's fine for local dev (this Next.js process
// and the Python pipeline that writes these files share one filesystem),
// but it does NOT work once "the admin who processes a slate" and "the
// member reading it" can be different hosted processes/machines -- a
// hosted member-facing server has no access to another server's local
// disk.
//
// This interface is the seam that change would go through. It is
// intentionally NOT wired into the existing loaders yet (lib/loaders.ts,
// lib/discovery.ts, and everything built on them) -- doing so is real,
// separate work for whenever hosting is actually implemented (see this
// module's docstring and Milestone 29's final report for what's still
// required). Building it now, unused, would violate this project's own
// "no premature abstraction" rule; this file exists solely so the
// interface shape is designed and reviewed ahead of time, with ONE real
// implementation (LocalStorageBackend, a thin wrapper around the exact
// fs calls lib/discovery.ts already makes) proving it's suffient for
// current behavior, and one documented stub (ProductionObjectStorageBackend)
// showing what a hosted backend would need to fill in. No vendor is
// chosen (S3 vs. GCS vs. Azure Blob vs. something else) since none is
// already used anywhere in this project.

export interface StorageBackend {
  /** Reads and JSON-parses a file at a repo-root-relative path (e.g.
   * "dfs_input/2026-08-19/dk_player_pool_....json"). Returns null for
   * "doesn't exist" or "isn't valid JSON" -- never throws for those
   * expected cases, matching lib/discovery.ts::safeReadJson's contract. */
  readJson<T>(relativePath: string): Promise<T | null>;

  /** True if a file exists at this path. */
  exists(relativePath: string): Promise<boolean>;

  /** Every filename in `dirRelativePath` starting with `prefix` and
   * ending with `ext`, sorted ascending (oldest/lowest-timestamp first)
   * -- mirrors lib/discovery.ts::findAllFiles. Empty array, never a
   * throw, when the directory doesn't exist. */
  listFiles(dirRelativePath: string, prefix: string, ext?: string): Promise<string[]>;

  /** The single newest matching file's relative path, or null -- mirrors
   * lib/discovery.ts::findLatestFile. */
  latestFile(dirRelativePath: string, prefix: string, ext?: string): Promise<string | null>;
}

/** Reads/lists from local disk relative to getArtifactRoot() -- the
 * exact same resolution lib/artifactRoot.ts already uses, so swapping
 * every existing loader over to this interface (future work, not done
 * in this milestone) would be behavior-neutral for local dev. */
export class LocalStorageBackend implements StorageBackend {
  constructor(private readonly rootDir: string) {}

  async readJson<T>(relativePath: string): Promise<T | null> {
    const fs = await import("node:fs");
    const path = await import("node:path");
    try {
      const raw = fs.readFileSync(path.join(this.rootDir, relativePath), "utf-8");
      return JSON.parse(raw) as T;
    } catch {
      return null;
    }
  }

  async exists(relativePath: string): Promise<boolean> {
    const fs = await import("node:fs");
    const path = await import("node:path");
    try {
      return fs.existsSync(path.join(this.rootDir, relativePath));
    } catch {
      return false;
    }
  }

  async listFiles(dirRelativePath: string, prefix: string, ext = ".json"): Promise<string[]> {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const dir = path.join(this.rootDir, dirRelativePath);
    try {
      return fs
        .readdirSync(dir)
        .filter((name) => name.startsWith(prefix) && name.endsWith(ext))
        .sort()
        .map((name) => path.join(dirRelativePath, name));
    } catch {
      return [];
    }
  }

  async latestFile(dirRelativePath: string, prefix: string, ext = ".json"): Promise<string | null> {
    const files = await this.listFiles(dirRelativePath, prefix, ext);
    return files.length ? files[files.length - 1] : null;
  }
}

/** Documented stub for a future hosted deployment. Deliberately throws
 * on every call rather than silently falling back to local disk (which
 * would be wrong -- a hosted process reading "local disk" would just
 * read its own empty/unrelated filesystem, not the admin's artifacts,
 * and fail in a much more confusing way later). Whoever wires up real
 * hosting fills this in once a concrete backend is chosen:
 *
 * - An object-storage client (AWS S3 / Google Cloud Storage / Azure
 *   Blob / R2 / ...) authenticated via environment-provided credentials
 *   (never hard-coded), mirroring how this project already keeps every
 *   other secret out of source (see dfs/providers/config.py's
 *   DFS_PROVIDER_API_KEY pattern).
 * - `readJson`/`exists` become a GET (or HEAD) request against
 *   `${bucket}/${relativePath}`.
 * - `listFiles`/`latestFile` become a prefix-listing call
 *   (e.g. S3 ListObjectsV2 with Prefix) instead of a directory read.
 * - The Python pipeline's own save side (research/prediction_snapshot.py,
 *   dfs/persistence.py, native_projections/persistence.py, etc.) would
 *   need the SAME backend choice on the write side, so an admin's
 *   Process/Refresh run uploads into the same bucket a hosted member
 *   read serves from -- that is a separate, larger change this
 *   milestone does not make (see the final report's "Hosting changes
 *   still required" section). */
export class ProductionObjectStorageBackend implements StorageBackend {
  async readJson<T>(relativePath: string): Promise<T | null> {
    throw new Error(
      `ProductionObjectStorageBackend is not configured -- no object-storage vendor has been chosen yet. ` +
        `Attempted to read: ${relativePath}`,
    );
  }

  async exists(relativePath: string): Promise<boolean> {
    throw new Error(`ProductionObjectStorageBackend is not configured. Attempted to check: ${relativePath}`);
  }

  async listFiles(dirRelativePath: string, prefix: string, ext = ".json"): Promise<string[]> {
    throw new Error(`ProductionObjectStorageBackend is not configured. Attempted to list: ${dirRelativePath}/${prefix}*${ext}`);
  }

  async latestFile(dirRelativePath: string, prefix: string, ext = ".json"): Promise<string | null> {
    throw new Error(`ProductionObjectStorageBackend is not configured. Attempted to find latest in: ${dirRelativePath}/${prefix}*${ext}`);
  }
}
