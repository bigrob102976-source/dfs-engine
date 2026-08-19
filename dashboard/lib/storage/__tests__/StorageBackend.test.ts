import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { LocalStorageBackend, ProductionObjectStorageBackend } from "../StorageBackend";

let tmpDir: string;

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-storage-backend-"));
});

afterEach(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("LocalStorageBackend", () => {
  it("readJson returns the parsed file when it exists", async () => {
    fs.mkdirSync(path.join(tmpDir, "dfs_input", "2026-08-19"), { recursive: true });
    fs.writeFileSync(path.join(tmpDir, "dfs_input", "2026-08-19", "pool.json"), JSON.stringify({ ok: true }));

    const backend = new LocalStorageBackend(tmpDir);
    const data = await backend.readJson<{ ok: boolean }>("dfs_input/2026-08-19/pool.json");
    expect(data).toEqual({ ok: true });
  });

  it("readJson returns null (never throws) for a missing file", async () => {
    const backend = new LocalStorageBackend(tmpDir);
    expect(await backend.readJson("does/not/exist.json")).toBeNull();
  });

  it("readJson returns null for invalid JSON", async () => {
    fs.mkdirSync(path.join(tmpDir, "x"), { recursive: true });
    fs.writeFileSync(path.join(tmpDir, "x", "bad.json"), "{not valid json");
    const backend = new LocalStorageBackend(tmpDir);
    expect(await backend.readJson("x/bad.json")).toBeNull();
  });

  it("exists reflects real file presence", async () => {
    fs.mkdirSync(path.join(tmpDir, "x"), { recursive: true });
    fs.writeFileSync(path.join(tmpDir, "x", "present.json"), "{}");
    const backend = new LocalStorageBackend(tmpDir);
    expect(await backend.exists("x/present.json")).toBe(true);
    expect(await backend.exists("x/absent.json")).toBe(false);
  });

  it("listFiles returns matching files sorted ascending, [] for a missing directory", async () => {
    fs.mkdirSync(path.join(tmpDir, "native_projection_snapshots", "2026-08-19"), { recursive: true });
    fs.writeFileSync(path.join(tmpDir, "native_projection_snapshots", "2026-08-19", "native_projection_2.json"), "{}");
    fs.writeFileSync(path.join(tmpDir, "native_projection_snapshots", "2026-08-19", "native_projection_1.json"), "{}");
    fs.writeFileSync(path.join(tmpDir, "native_projection_snapshots", "2026-08-19", "other_file.json"), "{}");

    const backend = new LocalStorageBackend(tmpDir);
    const files = await backend.listFiles("native_projection_snapshots/2026-08-19", "native_projection_");
    expect(files.map((f) => path.basename(f))).toEqual(["native_projection_1.json", "native_projection_2.json"]);

    expect(await backend.listFiles("no/such/dir", "x_")).toEqual([]);
  });

  it("latestFile returns the newest-sorted match, null when none exist", async () => {
    fs.mkdirSync(path.join(tmpDir, "d"), { recursive: true });
    fs.writeFileSync(path.join(tmpDir, "d", "snap_0000000001.json"), "{}");
    fs.writeFileSync(path.join(tmpDir, "d", "snap_0000000002.json"), "{}");

    const backend = new LocalStorageBackend(tmpDir);
    const latest = await backend.latestFile("d", "snap_");
    expect(latest && path.basename(latest)).toBe("snap_0000000002.json");
    expect(await backend.latestFile("d", "nonexistent_prefix_")).toBeNull();
  });
});

describe("ProductionObjectStorageBackend", () => {
  it("every method throws a clear 'not configured' error rather than silently falling back to local disk", async () => {
    const backend = new ProductionObjectStorageBackend();
    await expect(backend.readJson("x.json")).rejects.toThrow(/not configured/i);
    await expect(backend.exists("x.json")).rejects.toThrow(/not configured/i);
    await expect(backend.listFiles("dir", "p_")).rejects.toThrow(/not configured/i);
    await expect(backend.latestFile("dir", "p_")).rejects.toThrow(/not configured/i);
  });
});
