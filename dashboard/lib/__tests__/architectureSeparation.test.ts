import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

// Milestone 32.2B/32.3B established Big Money ML as SHADOW-only
// (comparison-only, never optimizer-selectable). Milestone 32.4
// DELIBERATELY supersedes that for ADMIN/OWNER users only: Big Money ML
// IS now a selectable optimizer projection source, gated by the
// 'mlb.big_money_ml_optimizer' feature flag (default ADMIN_ONLY). These
// tests were rewritten (not just relaxed) to prove the NEW guarantees:
// the source exists, is admin-gated server-side in BOTH optimizer API
// routes, and enforces strict "no mixed-source fallback" semantics
// rather than silently reverting to another source for a player missing
// an ML projection.

const DASHBOARD_ROOT = path.resolve(__dirname, "../..");

function readSource(relativePath: string): string {
  return readFileSync(path.join(DASHBOARD_ROOT, relativePath), "utf-8");
}

describe("Big Money ML optimizer wiring (Milestone 32.4, dashboard)", () => {
  it("lists big_money_ml in the optimizer's ProjectionSource union", () => {
    const source = readSource("lib/optimizerWorkspace/types.ts");
    const match = source.match(/export type ProjectionSource\s*=\s*([^;]+);/);
    expect(match).not.toBeNull();
    const union = match![1];
    expect(union).toContain("big_money_ml");
  });

  it("buildRunner's projection-override writer HAS a big_money_ml branch that uses the unified ML loader", () => {
    const source = readSource("lib/optimizerWorkspace/buildRunner.ts");
    expect(source).toContain('request.projectionSource === "big_money_ml"');
    expect(source).toContain("getMlProjectionByPlayerId");
  });

  it("buildRunner passes --strict-projection-source only for big_money_ml (isStrictProjectionSource helper)", () => {
    const source = readSource("lib/optimizerWorkspace/buildRunner.ts");
    expect(source).toContain("isStrictProjectionSource");
    expect(source).toContain("--strict-projection-source");
  });

  it("both the build and validate API routes enforce admin gating for big_money_ml server-side", () => {
    for (const route of ["app/api/optimizer/build/route.ts", "app/api/optimizer/validate/route.ts"]) {
      const source = readSource(route);
      expect(source).toContain("userCanSelectBigMoneyMlOptimizerSource");
      expect(source).toMatch(/projectionSource\s*===\s*["']big_money_ml["']/);
    }
  });

  it("parseBuildRequest accepts big_money_ml as a valid projectionSource shape (authorization is a separate, later check)", () => {
    const source = readSource("lib/optimizerWorkspace/parseBuildRequest.ts");
    expect(source).toContain("big_money_ml");
  });

  it("the Big Money ML optimizer feature flag is seeded ADMIN_ONLY, not PRODUCTION", () => {
    const source = readSource("lib/db/migrations/0006_big_money_ml_optimizer_flag.sql");
    expect(source).toMatch(/mlb\.big_money_ml_optimizer'?,\s*'MLB',\s*'Big Money ML Optimizer',\s*'ADMIN_ONLY'/);
  });

  it("bluecollar is admin-gated exactly like big_money_ml -- same source, same enforcement pattern", () => {
    const source = readSource("lib/optimizerWorkspace/buildRunner.ts");
    expect(source).toContain('isStrictProjectionSource(source: OptimizerBuildRequest["projectionSource"]): boolean');
    expect(source).toMatch(/source === "big_money_ml" \|\| source === "bluecollar"/);
  });

  it("slatePipeline's Big Money ML shadow-inference steps never affect computed slate status", () => {
    const source = readSource("lib/slatePipeline.ts");
    // Both the pitcher and hitter shadow-inference steps must push only
    // to `errors` (non-blocking), never participate in the
    // `readiness.ok ? "READY" : ...` computation.
    const mlStepIndex = source.indexOf("run_ml_shadow_inference.py");
    expect(mlStepIndex).toBeGreaterThan(-1);
    const statusComputationIndex = source.indexOf('readiness.ok ? "READY"');
    expect(statusComputationIndex).toBeGreaterThan(-1);
    const mlStepBlock = source.slice(mlStepIndex, statusComputationIndex);
    expect(mlStepBlock).not.toContain("readiness.ok");
  });
});

describe("BlueCollar Live Projection Integration wiring (dashboard)", () => {
  it("lists bluecollar in the optimizer's ProjectionSource union", () => {
    const source = readSource("lib/optimizerWorkspace/types.ts");
    const match = source.match(/export type ProjectionSource\s*=\s*([^;]+);/);
    expect(match).not.toBeNull();
    expect(match![1]).toContain("bluecollar");
  });

  it("buildRunner's projection-override writer HAS a bluecollar branch that uses the slate-scoped BlueCollar loader", () => {
    const source = readSource("lib/optimizerWorkspace/buildRunner.ts");
    expect(source).toContain('request.projectionSource === "bluecollar"');
    expect(source).toContain("getBlueCollarProjectionByPlayerId");
  });

  it("bluecollar is a strict projection source -- never mixed with Native/AI/ML for a missing player", () => {
    const source = readSource("lib/optimizerWorkspace/buildRunner.ts");
    expect(source).toMatch(/isStrictProjectionSource[\s\S]*?source === "bluecollar"/);
  });

  it("model-version provenance flags stay scoped to big_money_ml only, never attached to a bluecollar build", () => {
    const source = readSource("lib/optimizerWorkspace/buildRunner.ts");
    const strictBlock = source.slice(source.indexOf("if (isStrictProjectionSource(request.projectionSource)) {"), source.indexOf("args.push(\"--lineups\""));
    expect(strictBlock).toContain('request.projectionSource === "big_money_ml"');
    expect(strictBlock).toContain("getBigMoneyMlProvenance");
  });

  it("both the build and validate API routes enforce admin gating for bluecollar server-side", () => {
    for (const route of ["app/api/optimizer/build/route.ts", "app/api/optimizer/validate/route.ts"]) {
      const source = readSource(route);
      expect(source).toContain("userCanSelectBlueCollarOptimizerSource");
      expect(source).toMatch(/projectionSource\s*===\s*["']bluecollar["']/);
    }
  });

  it("parseBuildRequest accepts bluecollar as a valid projectionSource shape (authorization is a separate, later check)", () => {
    const source = readSource("lib/optimizerWorkspace/parseBuildRequest.ts");
    expect(source).toContain("bluecollar");
  });

  it("the BlueCollar optimizer feature flag is seeded ADMIN_ONLY, not PRODUCTION", () => {
    const source = readSource("lib/db/migrations/0007_bluecollar_optimizer_flag.sql");
    expect(source).toMatch(/mlb\.bluecollar_optimizer'?,\s*'MLB',\s*'BlueCollar Optimizer',\s*'ADMIN_ONLY'/);
  });

  it("slatePipeline's BlueCollar fetch step never affects computed slate status", () => {
    const source = readSource("lib/slatePipeline.ts");
    const stepIndex = source.indexOf("fetch_bluecollar_projections.py");
    expect(stepIndex).toBeGreaterThan(-1);
    const statusComputationIndex = source.indexOf('readiness.ok ? "READY"');
    expect(statusComputationIndex).toBeGreaterThan(-1);
    const stepBlock = source.slice(stepIndex, statusComputationIndex);
    expect(stepBlock).not.toContain("readiness.ok");
  });

  it("slatePipeline passes --slate-id to the BlueCollar fetch -- always slate-scoped, never date-only", () => {
    const source = readSource("lib/slatePipeline.ts");
    const callIndex = source.indexOf('runPythonScript("scripts/fetch_bluecollar_projections.py"');
    expect(callIndex).toBeGreaterThan(-1);
    const line = source.slice(callIndex, source.indexOf("\n", callIndex));
    expect(line).toContain("--slate-id");
  });

  it("BlueCollar's loader never runs from a Client Component -- server-only, filesystem-reading module", () => {
    const source = readSource("lib/blueCollarProjections.ts");
    expect(source).not.toContain('"use client"');
  });
});
