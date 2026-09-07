import { beforeEach, describe, expect, it } from "vitest";

import { loadLockExcludeState, saveLockExcludeState } from "./lockExcludeStorage";

describe("lockExcludeStorage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("returns empty state when nothing saved yet", () => {
    expect(loadLockExcludeState(151307)).toEqual({ locks: [], excludes: [] });
  });

  it("round-trips real DraftKings player identity strings", () => {
    saveLockExcludeState(151307, { locks: ["1214154"], excludes: ["877745"] });
    expect(loadLockExcludeState(151307)).toEqual({ locks: ["1214154"], excludes: ["877745"] });
  });

  it("keeps state scoped per DraftGroup -- a slate switch never leaks locks", () => {
    saveLockExcludeState(151307, { locks: ["1214154"], excludes: [] });
    expect(loadLockExcludeState(999999)).toEqual({ locks: [], excludes: [] });
  });
});
