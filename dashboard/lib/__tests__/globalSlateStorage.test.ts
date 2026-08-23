import { afterEach, describe, expect, it } from "vitest";

import { readStoredSlateId, writeStoredSlateId } from "../globalSlateStorage";

afterEach(() => {
  window.localStorage.clear();
});

describe("globalSlateStorage", () => {
  it("returns null when nothing has been stored", () => {
    expect(readStoredSlateId()).toBeNull();
  });

  it("round-trips a stored slate id", () => {
    writeStoredSlateId("dkunofficial-152547");
    expect(readStoredSlateId()).toBe("dkunofficial-152547");
  });

  it("clears the stored value when written with null -- Full Day is an explicit choice, not a stale gap", () => {
    writeStoredSlateId("dkunofficial-152547");
    writeStoredSlateId(null);
    expect(readStoredSlateId()).toBeNull();
  });

  it("overwrites a previously stored slate id with a new selection", () => {
    writeStoredSlateId("main");
    writeStoredSlateId("turbo");
    expect(readStoredSlateId()).toBe("turbo");
  });
});
