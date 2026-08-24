import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { artifactPath, toArtifactKey } from "../artifactRoot";

// Milestone 33.2 Part 18: cross-language object-key contract test -- the
// Node half. See tests/test_artifact_key_contract.py (the Python half)
// for why this exists: both languages must derive the SAME object key
// from the SAME logical artifact path, or a Python writer and a Node.js
// reader would silently disagree about where an artifact lives in the
// shared bucket. Both halves read the SAME fixture file so a case can
// never be added to one side's expectations without the other.

interface ContractCase {
  description: string;
  segments: string[];
  expectedKey: string;
}

const FIXTURE_PATH = path.resolve(__dirname, "../../../tests/fixtures/artifact_key_contract.json");

function loadCases(): ContractCase[] {
  return JSON.parse(fs.readFileSync(FIXTURE_PATH, "utf-8"));
}

describe("toArtifactKey cross-language contract", () => {
  it("the shared fixture file is non-empty", () => {
    expect(loadCases().length).toBeGreaterThanOrEqual(5);
  });

  it("matches the shared contract for every case, built the way every real caller builds a path (artifactPath())", () => {
    for (const testCase of loadCases()) {
      const absolute = artifactPath(...testCase.segments);
      expect(toArtifactKey(absolute), testCase.description).toBe(testCase.expectedKey);
    }
  });

  it("matches the shared contract from an already-relative path too", () => {
    for (const testCase of loadCases()) {
      const relative = testCase.segments.join(path.sep);
      expect(toArtifactKey(relative), testCase.description).toBe(testCase.expectedKey);
    }
  });
});
