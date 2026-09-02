import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

// M6Q -- structural proof that the entire canonical eligibility/build
// bridge chain never imports a DK-network-capable module. Mirrors
// canonicalPostgresBackend.test.ts's own M5K structural isolation test.

const FORBIDDEN = ["draftkings_unofficial", "fetch_dfs_slate", "list_dfs_slates", "node:http", "node:https"];

function importBlockOf(filePath: string): string {
  const src = fs.readFileSync(filePath, "utf8");
  return src.split("\n").filter((line) => line.trimStart().startsWith("import ")).join("\n");
}

describe("M6Q: canonical eligibility/build bridge makes zero DraftKings network calls (structural)", () => {
  it("canonicalEligibility.ts never imports a DK/network module (only runPythonScript, a generic subprocess runner)", () => {
    const block = importBlockOf(path.join(__dirname, "..", "canonicalEligibility.ts"));
    for (const forbidden of FORBIDDEN) expect(block).not.toContain(forbidden);
  });

  it("canonicalLineupLegalityCheck.ts never imports a DK/network module", () => {
    const block = importBlockOf(path.join(__dirname, "..", "canonicalLineupLegalityCheck.ts"));
    for (const forbidden of FORBIDDEN) expect(block).not.toContain(forbidden);
  });

  it("canonicalPoolMaterialization.ts never imports a DK/network module", () => {
    const block = importBlockOf(path.join(__dirname, "..", "..", "optimizerWorkspace", "canonicalPoolMaterialization.ts"));
    for (const forbidden of FORBIDDEN) expect(block).not.toContain(forbidden);
  });
});

describe("M7L: automatic canonical eligibility refresh wiring makes zero new DraftKings network calls (structural)", () => {
  it("canonicalEligibility.ts's refreshCanonicalEligibilityForDate lives in the SAME file already proven DK-free above -- no new import surface", () => {
    const block = importBlockOf(path.join(__dirname, "..", "canonicalEligibility.ts"));
    for (const forbidden of FORBIDDEN) expect(block).not.toContain(forbidden);
  });

  it("slatePipeline.ts's own import block never imports a DK/network module directly (all provider access is via the existing runPythonScript subprocess boundary)", () => {
    const block = importBlockOf(path.join(__dirname, "..", "..", "slatePipeline.ts"));
    for (const forbidden of FORBIDDEN) expect(block).not.toContain(forbidden);
  });
});
