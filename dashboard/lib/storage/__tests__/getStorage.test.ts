import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { LocalStorageBackend } from "../StorageBackend";
import { __resetStorageForTests, __setStorageForTests, getStorage } from "../getStorage";

// Milestone 33.2 Part 19: restart-safety simulation for the Node side --
// mirrors lib/db/__tests__/executor.test.ts's own pattern for
// __resetExecutorForTests(). getStorage() holds no artifact CONTENT of
// its own (only a backend selection); __resetStorageForTests() forces
// the next call to rebuild from scratch, simulating a fresh process --
// a real restart's "worker just came back up" moment.

let root: string;

beforeEach(() => {
  root = fs.mkdtempSync(path.join(os.tmpdir(), "getStorage-restart-"));
  __resetStorageForTests();
});

afterEach(() => {
  __resetStorageForTests();
  fs.rmSync(root, { recursive: true, force: true });
});

describe("getStorage restart safety", () => {
  it("a fresh singleton (post-reset) resolves an artifact a prior instance persisted", async () => {
    __setStorageForTests(new LocalStorageBackend(root));
    await getStorage().readJson("does/not/matter.json"); // warm the "process"
    fs.mkdirSync(path.join(root, "predictions", "2026-08-19"), { recursive: true });
    fs.writeFileSync(path.join(root, "predictions", "2026-08-19", "pitcher_board_1.json"), JSON.stringify({ generated_at: "2026-08-19T12:00:00Z" }));

    __resetStorageForTests(); // simulates the process restarting
    __setStorageForTests(new LocalStorageBackend(root)); // the new process resolves its backend the same way getStorage() itself would

    const reread = await getStorage().readJson<{ generated_at: string }>("predictions/2026-08-19/pitcher_board_1.json");
    expect(reread).toEqual({ generated_at: "2026-08-19T12:00:00Z" });
  });

  it("getStorage() itself is a lazy singleton -- two calls without a reset return the identical instance", () => {
    __setStorageForTests(new LocalStorageBackend(root));
    const first = getStorage();
    const second = getStorage();
    expect(first).toBe(second);
  });
});
