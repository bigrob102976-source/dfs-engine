import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

// Milestone 32.2B -- TypeScript-side companion to
// tests/test_architecture_separation.py's Python-side checks: proves
// Big Money ML stays SHADOW-only on the dashboard side too. Big Money
// ML is a comparison-only signal (Projection Lab column, Player Detail
// section, informational Command Center card) -- it must never become a
// selectable optimizer projection source or influence the build.

const DASHBOARD_ROOT = path.resolve(__dirname, "../..");

function readSource(relativePath: string): string {
  return readFileSync(path.join(DASHBOARD_ROOT, relativePath), "utf-8");
}

describe("Big Money ML shadow-mode isolation (dashboard)", () => {
  it("never lists big_money_ml in the optimizer's ProjectionSource union", () => {
    const source = readSource("lib/optimizerWorkspace/types.ts");
    const match = source.match(/export type ProjectionSource\s*=\s*([^;]+);/);
    expect(match).not.toBeNull();
    const union = match![1];
    expect(union).not.toContain("big_money_ml");
    expect(union).not.toContain("ml_shadow");
  });

  it("buildRunner's projection-override writer has no ML branch", () => {
    const source = readSource("lib/optimizerWorkspace/buildRunner.ts");
    expect(source).not.toContain("mlProjection");
    expect(source).not.toContain("big_money_ml");
  });

  it("the optimizer build request/response types never mention big_money_ml", () => {
    const source = readSource("lib/optimizerWorkspace/types.ts");
    // mlProjection/mlDataQualityScore/mlProjectionStatus ARE expected on
    // PoolPlayerRow (comparison-only fields) -- this test only guards
    // against the literal optimizer SOURCE token, checked above and
    // never assigned to `projectionSource`.
    expect(source).not.toMatch(/projectionSource\s*:\s*["']big_money_ml["']/);
  });

  it("slatePipeline's Big Money ML step never affects computed slate status", () => {
    const source = readSource("lib/slatePipeline.ts");
    // The ML step must push only to `errors` (non-blocking), never
    // participate in the `readiness.ok ? "READY" : ...` computation.
    const mlStepIndex = source.indexOf("run_ml_shadow_inference.py");
    expect(mlStepIndex).toBeGreaterThan(-1);
    const statusComputationIndex = source.indexOf('readiness.ok ? "READY"');
    expect(statusComputationIndex).toBeGreaterThan(-1);
    const mlStepBlock = source.slice(mlStepIndex, statusComputationIndex);
    expect(mlStepBlock).not.toContain("readiness.ok");
  });
});
