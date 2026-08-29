import { describe, expect, it } from "vitest";

import { runObjectStorageReadCheck } from "../objectStorageReadCheck";
import type { StorageBackend } from "../StorageBackend";

function fakeBackend(overrides: { readJsonReturns?: unknown; exists?: () => Promise<boolean> } = {}): StorageBackend {
  return {
    readJson: async <T>() => (overrides.readJsonReturns as T | null) ?? null,
    exists: overrides.exists ?? (async () => false),
    listFiles: async () => [],
    latestFile: async () => null,
    listSubdirectories: async () => [],
  };
}

describe("runObjectStorageReadCheck", () => {
  it("reports allOk when the key exists and its content has smoke_test: true", async () => {
    const storage = fakeBackend({
      exists: async () => true,
      readJsonReturns: { smoke_test: true, source: "scripts/smoke_test_object_storage.py" },
    });
    const result = await runObjectStorageReadCheck(storage, "healthchecks/r2-smoke-test.txt");
    expect(result).toEqual({ exists: true, readable: true, contentLooksValid: true, allOk: true });
  });

  it("reports not ok when the key doesn't exist", async () => {
    const storage = fakeBackend({ exists: async () => false });
    const result = await runObjectStorageReadCheck(storage, "healthchecks/r2-smoke-test.txt");
    expect(result.allOk).toBe(false);
    expect(result.exists).toBe(false);
    expect(result.readable).toBe(false);
  });

  it("reports not ok when the object exists but its content doesn't look like this smoke test's own payload", async () => {
    const storage = fakeBackend({
      exists: async () => true,
      readJsonReturns: { some_other_artifact: true },
    });
    const result = await runObjectStorageReadCheck(storage, "healthchecks/r2-smoke-test.txt");
    expect(result.exists).toBe(true);
    expect(result.readable).toBe(true);
    expect(result.contentLooksValid).toBe(false);
    expect(result.allOk).toBe(false);
  });

  it("reports not ok when exists() is true but readJson() can't parse the content (e.g. not valid JSON)", async () => {
    const storage = fakeBackend({ exists: async () => true });
    const result = await runObjectStorageReadCheck(storage, "healthchecks/r2-smoke-test.txt");
    expect(result.readable).toBe(false);
    expect(result.allOk).toBe(false);
  });
});
