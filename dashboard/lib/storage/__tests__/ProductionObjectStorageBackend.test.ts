import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Fakes the S3 wire protocol entirely -- per this milestone's "no real
// cloud resources required in unit tests" instruction, this proves the
// backend's REQUEST-BUILDING and RESPONSE-HANDLING logic (correct
// Bucket/Key/Prefix, NotFound -> null/false/[], JSON parsing, ext
// filtering + sort) without ever making a real network call.
const { mockSend } = vi.hoisted(() => ({ mockSend: vi.fn() }));

vi.mock("@aws-sdk/client-s3", () => {
  class FakeCommand {
    constructor(public input: Record<string, unknown>) {}
  }
  class FakeS3Client {
    send = mockSend;
  }
  return {
    S3Client: FakeS3Client,
    GetObjectCommand: class GetObjectCommand extends FakeCommand {},
    HeadObjectCommand: class HeadObjectCommand extends FakeCommand {},
    ListObjectsV2Command: class ListObjectsV2Command extends FakeCommand {},
  };
});

import { getObjectStorageConfigStatus, ProductionObjectStorageBackend, resolveObjectStorageConfigFromEnv, type ObjectStorageConfig } from "../StorageBackend";

const CONFIG: ObjectStorageConfig = {
  region: "auto",
  bucket: "bigmoney-artifacts",
  accessKeyId: "AKIAFAKE",
  secretAccessKey: "fakeSecret",
  endpoint: "https://fake.r2.cloudflarestorage.com",
};

beforeEach(() => {
  mockSend.mockReset();
});

describe("resolveObjectStorageConfigFromEnv / getObjectStorageConfigStatus", () => {
  const ENV_KEYS = ["OBJECT_STORAGE_ENDPOINT", "OBJECT_STORAGE_REGION", "OBJECT_STORAGE_BUCKET", "OBJECT_STORAGE_ACCESS_KEY", "OBJECT_STORAGE_SECRET_KEY"] as const;
  let originalEnv: Record<string, string | undefined>;

  beforeEach(() => {
    originalEnv = Object.fromEntries(ENV_KEYS.map((k) => [k, process.env[k]]));
    for (const k of ENV_KEYS) delete (process.env as Record<string, string | undefined>)[k];
  });

  afterEach(() => {
    for (const [k, v] of Object.entries(originalEnv)) {
      if (v === undefined) delete (process.env as Record<string, string | undefined>)[k];
      else (process.env as Record<string, string | undefined>)[k] = v;
    }
  });

  it("resolves null and reports missing var names when unconfigured", () => {
    expect(resolveObjectStorageConfigFromEnv()).toBeNull();
    const status = getObjectStorageConfigStatus();
    expect(status.configured).toBe(false);
    if (!status.configured) {
      expect(status.missing).toEqual(["OBJECT_STORAGE_REGION", "OBJECT_STORAGE_BUCKET", "OBJECT_STORAGE_ACCESS_KEY", "OBJECT_STORAGE_SECRET_KEY"]);
    }
  });

  it("resolves a full config once all four required vars are set (endpoint stays optional)", () => {
    (process.env as Record<string, string | undefined>).OBJECT_STORAGE_REGION = "us-east-1";
    (process.env as Record<string, string | undefined>).OBJECT_STORAGE_BUCKET = "bkt";
    (process.env as Record<string, string | undefined>).OBJECT_STORAGE_ACCESS_KEY = "ak";
    (process.env as Record<string, string | undefined>).OBJECT_STORAGE_SECRET_KEY = "sk";
    expect(resolveObjectStorageConfigFromEnv()).toEqual({ region: "us-east-1", bucket: "bkt", accessKeyId: "ak", secretAccessKey: "sk", endpoint: undefined });
    expect(getObjectStorageConfigStatus()).toEqual({ configured: true });
  });
});

describe("ProductionObjectStorageBackend (configured, S3 client mocked)", () => {
  it("readJson issues a GetObjectCommand and parses the JSON body", async () => {
    mockSend.mockResolvedValueOnce({ Body: { transformToString: async () => JSON.stringify({ ok: true }) } });
    const backend = new ProductionObjectStorageBackend(CONFIG);
    const result = await backend.readJson<{ ok: boolean }>("dfs_input/2026-08-19/pool.json");
    expect(result).toEqual({ ok: true });
    expect(mockSend).toHaveBeenCalledTimes(1);
    const command = mockSend.mock.calls[0][0];
    expect(command.input).toEqual({ Bucket: "bigmoney-artifacts", Key: "dfs_input/2026-08-19/pool.json" });
  });

  it("readJson returns null (never throws) when the key doesn't exist", async () => {
    const err = Object.assign(new Error("not found"), { name: "NoSuchKey" });
    mockSend.mockRejectedValueOnce(err);
    const backend = new ProductionObjectStorageBackend(CONFIG);
    expect(await backend.readJson("missing.json")).toBeNull();
  });

  it("exists returns true/false based on HeadObjectCommand success vs NotFound", async () => {
    mockSend.mockResolvedValueOnce({});
    const backend = new ProductionObjectStorageBackend(CONFIG);
    expect(await backend.exists("present.json")).toBe(true);

    mockSend.mockRejectedValueOnce(Object.assign(new Error("nope"), { name: "NotFound" }));
    expect(await backend.exists("absent.json")).toBe(false);
  });

  it("listFiles builds the correct dir+prefix Key prefix, filters by ext, and sorts", async () => {
    mockSend.mockResolvedValueOnce({
      Contents: [
        { Key: "native_projection_snapshots/2026-08-19/native_projection_2.json" },
        { Key: "native_projection_snapshots/2026-08-19/native_projection_1.json" },
        { Key: "native_projection_snapshots/2026-08-19/native_projection_1.txt" }, // wrong ext, excluded
      ],
    });
    const backend = new ProductionObjectStorageBackend(CONFIG);
    const files = await backend.listFiles("native_projection_snapshots/2026-08-19", "native_projection_");
    expect(files).toEqual([
      "native_projection_snapshots/2026-08-19/native_projection_1.json",
      "native_projection_snapshots/2026-08-19/native_projection_2.json",
    ]);
    const command = mockSend.mock.calls[0][0];
    expect(command.input).toEqual({ Bucket: "bigmoney-artifacts", Prefix: "native_projection_snapshots/2026-08-19/native_projection_" });
  });

  it("latestFile returns the newest-sorted match, null when none exist", async () => {
    mockSend.mockResolvedValueOnce({ Contents: [{ Key: "d/snap_0000000001.json" }, { Key: "d/snap_0000000002.json" }] });
    const backend = new ProductionObjectStorageBackend(CONFIG);
    expect(await backend.latestFile("d", "snap_")).toBe("d/snap_0000000002.json");

    mockSend.mockResolvedValueOnce({ Contents: [] });
    const backend2 = new ProductionObjectStorageBackend(CONFIG);
    expect(await backend2.latestFile("d", "nonexistent_")).toBeNull();
  });
});

describe("ProductionObjectStorageBackend (unconfigured)", () => {
  it("every method throws a clear 'not configured' error without ever calling the S3 client", async () => {
    const backend = new ProductionObjectStorageBackend(null);
    await expect(backend.readJson("x.json")).rejects.toThrow(/not configured/i);
    await expect(backend.exists("x.json")).rejects.toThrow(/not configured/i);
    await expect(backend.listFiles("dir", "p_")).rejects.toThrow(/not configured/i);
    await expect(backend.latestFile("dir", "p_")).rejects.toThrow(/not configured/i);
    expect(mockSend).not.toHaveBeenCalled();
  });
});
