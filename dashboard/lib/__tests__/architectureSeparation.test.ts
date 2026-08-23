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
