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
// current behavior.
//
// Milestone 30: ProductionObjectStorageBackend is now a real, working
// implementation against any S3-compatible provider (AWS S3, Cloudflare
// R2, Backblaze B2, MinIO, ...) via @aws-sdk/client-s3, configured
// entirely through five env vars (never hard-coded, matching this
// project's existing DFS_PROVIDER_API_KEY-style secret convention):
// OBJECT_STORAGE_ENDPOINT (optional -- omit for real AWS S3, required for
// every other S3-compatible provider), OBJECT_STORAGE_REGION,
// OBJECT_STORAGE_BUCKET, OBJECT_STORAGE_ACCESS_KEY, OBJECT_STORAGE_SECRET_KEY.
// Constructed with no config (or an unresolvable one), it preserves its
// original Milestone 29 behavior exactly: every method throws a clear
// "not configured" error rather than silently reading local disk.

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

  /** Milestone 33.2: immediate child "directory" names one level under
   * `dirRelativePath` -- e.g. the YYYY-MM-DD slate-date folders under an
   * artifact root, for lib/discovery.ts::listSlateDates. Local disk has
   * real directories; object storage has none, so this is derived from
   * key prefixes up to the next "/" (S3's own delimiter-listing
   * convention). Empty array, never a throw, when the "directory"
   * doesn't exist. Sorted ascending. */
  listSubdirectories(dirRelativePath: string): Promise<string[]>;
}

/** Reads/lists from local disk relative to getArtifactRoot() -- the
 * exact same resolution lib/artifactRoot.ts already uses, so swapping
 * every existing loader over to this interface (future work, not done
 * in this milestone) would be behavior-neutral for local dev. */
export class LocalStorageBackend implements StorageBackend {
  constructor(private readonly rootDir: string) {}

  /** Milestone 33.2: `relativePath` is USUALLY root-relative (the normal
   * case), but lib/artifactRoot.ts::toArtifactKey() deliberately returns
   * an already-ABSOLUTE string for a path outside the artifact root (a
   * scratch/temp path, or a test operating on its own tmpdir) rather
   * than erroring -- see that function's own docstring. `path.join`
   * does NOT special-case an absolute later segment the way Python's
   * pathlib `/` operator does, so joining an absolute `relativePath`
   * onto `rootDir` here would silently produce a garbage nested path.
   * This mirrors research/artifact_storage.py::LocalArtifactStorage's
   * identical behavior (Path.__truediv__ ignores `self` when the RHS is
   * absolute) so both languages resolve a fallback key the same way. */
  private async resolve(relativePath: string): Promise<string> {
    const path = await import("node:path");
    return path.normalize(path.isAbsolute(relativePath) ? relativePath : path.join(this.rootDir, relativePath));
  }

  async readJson<T>(relativePath: string): Promise<T | null> {
    const fs = await import("node:fs");
    try {
      const raw = fs.readFileSync(await this.resolve(relativePath), "utf-8");
      return JSON.parse(raw) as T;
    } catch {
      return null;
    }
  }

  async exists(relativePath: string): Promise<boolean> {
    const fs = await import("node:fs");
    try {
      return fs.existsSync(await this.resolve(relativePath));
    } catch {
      return false;
    }
  }

  async listFiles(dirRelativePath: string, prefix: string, ext = ".json"): Promise<string[]> {
    const fs = await import("node:fs");
    const dir = await this.resolve(dirRelativePath);
    // Milestone 33.2: joined with a literal "/", NOT path.join -- these
    // returned strings are KEYS (mirroring ProductionObjectStorageBackend's
    // S3 keys, always forward-slash), not native filesystem paths.
    // path.join normalizes to the OS-native separator (backslash on
    // Windows) even when its inputs already used "/", which would
    // silently break every caller that treats a returned key as an
    // S3-style, forward-slash string (e.g. lib/discovery.ts::safeListDir
    // splitting on "/" to get a bare filename).
    const keyPrefix = dirRelativePath.replace(/\\/g, "/").replace(/\/+$/, "");
    try {
      return fs
        .readdirSync(dir)
        .filter((name) => name.startsWith(prefix) && name.endsWith(ext))
        .sort()
        .map((name) => `${keyPrefix}/${name}`);
    } catch {
      return [];
    }
  }

  async latestFile(dirRelativePath: string, prefix: string, ext = ".json"): Promise<string | null> {
    const files = await this.listFiles(dirRelativePath, prefix, ext);
    return files.length ? files[files.length - 1] : null;
  }

  async listSubdirectories(dirRelativePath: string): Promise<string[]> {
    const fs = await import("node:fs");
    const dir = await this.resolve(dirRelativePath);
    try {
      return fs
        .readdirSync(dir, { withFileTypes: true })
        .filter((entry) => entry.isDirectory())
        .map((entry) => entry.name)
        .sort();
    } catch {
      return [];
    }
  }
}

export interface ObjectStorageConfig {
  /** Omit for real AWS S3 (its region-based default endpoint is used).
   * Required for every other S3-compatible provider (R2, B2, MinIO, ...). */
  endpoint?: string;
  region: string;
  bucket: string;
  accessKeyId: string;
  secretAccessKey: string;
}

const REQUIRED_OBJECT_STORAGE_ENV_VARS = [
  "OBJECT_STORAGE_REGION",
  "OBJECT_STORAGE_BUCKET",
  "OBJECT_STORAGE_ACCESS_KEY",
  "OBJECT_STORAGE_SECRET_KEY",
] as const;

/** Reads the five OBJECT_STORAGE_* env vars (exact names from this
 * milestone's spec). Returns null -- never throws -- when any required
 * var is missing, so callers can decide for themselves whether that's
 * fine (local dev) or fatal (production, see lib/storage/backend.ts). */
export function resolveObjectStorageConfigFromEnv(): ObjectStorageConfig | null {
  const region = process.env.OBJECT_STORAGE_REGION;
  const bucket = process.env.OBJECT_STORAGE_BUCKET;
  const accessKeyId = process.env.OBJECT_STORAGE_ACCESS_KEY;
  const secretAccessKey = process.env.OBJECT_STORAGE_SECRET_KEY;
  if (!region || !bucket || !accessKeyId || !secretAccessKey) return null;
  return { endpoint: process.env.OBJECT_STORAGE_ENDPOINT || undefined, region, bucket, accessKeyId, secretAccessKey };
}

/** SAFE status for the Admin System page (Milestone 30) -- never returns
 * a credential value, only which var names (not their contents) are
 * missing. Mirrors lib/billing/stripeConfig.ts::getStripeConfigStatus's
 * "nothing here ever logs or returns a secret VALUE" contract. */
export function getObjectStorageConfigStatus(): { configured: true } | { configured: false; missing: string[] } {
  const missing = REQUIRED_OBJECT_STORAGE_ENV_VARS.filter((name) => !process.env[name]);
  return missing.length === 0 ? { configured: true } : { configured: false, missing: [...missing] };
}

function isNotFoundError(err: unknown): boolean {
  const name = (err as { name?: string } | undefined)?.name;
  const statusCode = (err as { $metadata?: { httpStatusCode?: number } } | undefined)?.$metadata?.httpStatusCode;
  return name === "NoSuchKey" || name === "NotFound" || statusCode === 404;
}

/** Real S3-compatible object storage (AWS S3, Cloudflare R2, Backblaze
 * B2, MinIO, ...) -- vendor-neutral via the standard S3 API surface.
 * Configured entirely from env (see resolveObjectStorageConfigFromEnv);
 * constructed with no config (the default), every method throws a clear
 * "not configured" error rather than silently falling back to local disk
 * -- a hosted process reading "local disk" would just read its own
 * empty/unrelated filesystem, not the admin's artifacts, and fail in a
 * much more confusing way later.
 *
 * NOTE: the Python pipeline's own save side (research/prediction_snapshot.py,
 * dfs/persistence.py, native_projections/persistence.py, etc.) needs the
 * SAME backend choice on the write side, so an admin's Process/Refresh
 * run uploads into the same bucket a hosted member read serves from --
 * see native_projections/artifact_storage.py-equivalent work item and
 * DEPLOYMENT.md for what remains before this is fully wired end to end. */
type S3ClientModule = typeof import("@aws-sdk/client-s3");

export class ProductionObjectStorageBackend implements StorageBackend {
  private readonly config: ObjectStorageConfig | null;
  private clientPromise: Promise<{ mod: S3ClientModule; client: import("@aws-sdk/client-s3").S3Client }> | null = null;

  constructor(config: ObjectStorageConfig | null = resolveObjectStorageConfigFromEnv()) {
    this.config = config;
  }

  private async requireClient(): Promise<{ mod: S3ClientModule; client: import("@aws-sdk/client-s3").S3Client; bucket: string }> {
    const config = this.config;
    if (!config) {
      throw new Error(
        "ProductionObjectStorageBackend is not configured -- set OBJECT_STORAGE_REGION, OBJECT_STORAGE_BUCKET, " +
          "OBJECT_STORAGE_ACCESS_KEY, and OBJECT_STORAGE_SECRET_KEY (OBJECT_STORAGE_ENDPOINT is optional, only " +
          "needed for S3-compatible providers other than AWS S3 itself).",
      );
    }
    if (!this.clientPromise) {
      this.clientPromise = import("@aws-sdk/client-s3").then((mod) => ({
        mod,
        client: new mod.S3Client({
          region: config.region,
          endpoint: config.endpoint,
          // Path-style addressing is required by most non-AWS S3-compatible
          // providers when a custom endpoint is set; AWS S3 itself (no
          // custom endpoint) uses virtual-hosted-style as usual.
          forcePathStyle: Boolean(config.endpoint),
          credentials: { accessKeyId: config.accessKeyId, secretAccessKey: config.secretAccessKey },
        }),
      }));
    }
    const { mod, client } = await this.clientPromise;
    return { mod, client, bucket: config.bucket };
  }

  async readJson<T>(relativePath: string): Promise<T | null> {
    const { mod, client, bucket } = await this.requireClient();
    try {
      const result = await client.send(new mod.GetObjectCommand({ Bucket: bucket, Key: relativePath }));
      const body = await result.Body?.transformToString("utf-8");
      if (!body) return null;
      return JSON.parse(body) as T;
    } catch (err) {
      if (!isNotFoundError(err)) {
        console.error(`ProductionObjectStorageBackend.readJson failed for "${relativePath}":`, err instanceof Error ? err.message : err);
      }
      return null;
    }
  }

  async exists(relativePath: string): Promise<boolean> {
    const { mod, client, bucket } = await this.requireClient();
    try {
      await client.send(new mod.HeadObjectCommand({ Bucket: bucket, Key: relativePath }));
      return true;
    } catch (err) {
      if (!isNotFoundError(err)) {
        console.error(`ProductionObjectStorageBackend.exists failed for "${relativePath}":`, err instanceof Error ? err.message : err);
      }
      return false;
    }
  }

  async listFiles(dirRelativePath: string, prefix: string, ext = ".json"): Promise<string[]> {
    const { mod, client, bucket } = await this.requireClient();
    const keyPrefix = `${dirRelativePath.replace(/\/+$/, "")}/${prefix}`;
    try {
      const result = await client.send(new mod.ListObjectsV2Command({ Bucket: bucket, Prefix: keyPrefix }));
      return (result.Contents ?? [])
        .map((obj) => obj.Key)
        .filter((key): key is string => Boolean(key && key.endsWith(ext)))
        .sort();
    } catch (err) {
      console.error(`ProductionObjectStorageBackend.listFiles failed for prefix "${keyPrefix}":`, err instanceof Error ? err.message : err);
      return [];
    }
  }

  async latestFile(dirRelativePath: string, prefix: string, ext = ".json"): Promise<string | null> {
    const files = await this.listFiles(dirRelativePath, prefix, ext);
    return files.length ? files[files.length - 1] : null;
  }

  async listSubdirectories(dirRelativePath: string): Promise<string[]> {
    const { mod, client, bucket } = await this.requireClient();
    const keyPrefix = `${dirRelativePath.replace(/\/+$/, "")}/`;
    try {
      const result = await client.send(new mod.ListObjectsV2Command({ Bucket: bucket, Prefix: keyPrefix, Delimiter: "/" }));
      return (result.CommonPrefixes ?? [])
        .map((p) => p.Prefix)
        .filter((p): p is string => Boolean(p))
        .map((p) => p.slice(keyPrefix.length).replace(/\/+$/, ""))
        .filter((name) => name.length > 0)
        .sort();
    } catch (err) {
      console.error(`ProductionObjectStorageBackend.listSubdirectories failed for prefix "${keyPrefix}":`, err instanceof Error ? err.message : err);
      return [];
    }
  }
}

/** Real connectivity check -- used by the Admin System page's "Object
 * Storage" status card. HeadBucketCommand only confirms the bucket is
 * reachable with the configured credentials; it does not depend on any
 * particular key existing (unlike exists()/readJson(), which treat a
 * missing KEY as a normal, non-error outcome). Never throws; returns a
 * structured result so a connection failure renders as "ERROR", not a
 * 500. */
export async function checkObjectStorageConnection(config: ObjectStorageConfig): Promise<{ connected: boolean; error: string | null }> {
  try {
    const { S3Client, HeadBucketCommand } = await import("@aws-sdk/client-s3");
    const client = new S3Client({
      region: config.region,
      endpoint: config.endpoint,
      forcePathStyle: Boolean(config.endpoint),
      credentials: { accessKeyId: config.accessKeyId, secretAccessKey: config.secretAccessKey },
    });
    await client.send(new HeadBucketCommand({ Bucket: config.bucket }));
    return { connected: true, error: null };
  } catch (err) {
    return { connected: false, error: err instanceof Error ? err.message : String(err) };
  }
}
