import { describe, expect, it } from "vitest";

import { parseBuildRequest } from "../parseBuildRequest";

function baseBody(overrides: Record<string, unknown> = {}) {
  return { slateId: "mock-main-2026-08-12", lineups: 20, objective: "projection", ...overrides };
}

describe("parseBuildRequest", () => {
  it("accepts a minimal valid request and fills in sane defaults", () => {
    const result = parseBuildRequest(baseBody());
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.request.slateId).toBe("mock-main-2026-08-12");
    expect(result.request.lineups).toBe(20);
    expect(result.request.objective).toBe("projection");
    expect(result.request.locks).toEqual([]);
    expect(result.request.exclusions).toEqual([]);
    expect(result.request.maxExposure).toEqual({});
    expect(result.request.stackSize).toBeNull();
    expect(result.request.stackTeam).toBeNull();
    expect(result.request.allowPitcherVsHitter).toBe(false);
    expect(result.request.minSalary).toBeNull();
    expect(result.request.minUnique).toBe(2);
    expect(result.request.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("rejects a missing/invalid slateId", () => {
    expect(parseBuildRequest(baseBody({ slateId: undefined })).ok).toBe(false);
    expect(parseBuildRequest(baseBody({ slateId: "bad slate id!" })).ok).toBe(false);
    expect(parseBuildRequest(baseBody({ slateId: 12345 })).ok).toBe(false);
  });

  it("rejects lineups outside 1-150", () => {
    expect(parseBuildRequest(baseBody({ lineups: 0 })).ok).toBe(false);
    expect(parseBuildRequest(baseBody({ lineups: 151 })).ok).toBe(false);
    expect(parseBuildRequest(baseBody({ lineups: 1.5 })).ok).toBe(false);
    expect(parseBuildRequest(baseBody({ lineups: 150 })).ok).toBe(true);
    expect(parseBuildRequest(baseBody({ lineups: 1 })).ok).toBe(true);
  });

  it("rejects an unknown objective", () => {
    const result = parseBuildRequest(baseBody({ objective: "not_a_real_objective" }));
    expect(result.ok).toBe(false);
  });

  it("accepts every real objective mode", () => {
    for (const objective of ["projection", "ceiling", "balanced", "leverage"]) {
      expect(parseBuildRequest(baseBody({ objective })).ok).toBe(true);
    }
  });

  it("rejects locks/exclusions that aren't string arrays", () => {
    expect(parseBuildRequest(baseBody({ locks: "Paul Skenes" })).ok).toBe(false);
    expect(parseBuildRequest(baseBody({ locks: [1, 2] })).ok).toBe(false);
    expect(parseBuildRequest(baseBody({ exclusions: { name: "x" } })).ok).toBe(false);
  });

  it("accepts valid locks/exclusions", () => {
    const result = parseBuildRequest(baseBody({ locks: ["Paul Skenes"], exclusions: ["Some Player"] }));
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.request.locks).toEqual(["Paul Skenes"]);
      expect(result.request.exclusions).toEqual(["Some Player"]);
    }
  });

  it("rejects a maxExposure fraction outside 0-1", () => {
    expect(parseBuildRequest(baseBody({ maxExposure: { "Kyle Schwarber": 1.5 } })).ok).toBe(false);
    expect(parseBuildRequest(baseBody({ maxExposure: { "Kyle Schwarber": -0.1 } })).ok).toBe(false);
  });

  it("accepts a valid maxExposure map", () => {
    const result = parseBuildRequest(baseBody({ maxExposure: { "Kyle Schwarber": 0.5 } }));
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.request.maxExposure).toEqual({ "Kyle Schwarber": 0.5 });
  });

  it("rejects stackSize outside 2-5", () => {
    expect(parseBuildRequest(baseBody({ stackSize: 1 })).ok).toBe(false);
    expect(parseBuildRequest(baseBody({ stackSize: 6 })).ok).toBe(false);
  });

  it("accepts a null stackSize and a valid stackSize with a stackTeam", () => {
    expect(parseBuildRequest(baseBody({ stackSize: null })).ok).toBe(true);
    const result = parseBuildRequest(baseBody({ stackSize: 5, stackTeam: "PHI" }));
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.request.stackSize).toBe(5);
      expect(result.request.stackTeam).toBe("PHI");
    }
  });

  it("rejects a negative minSalary", () => {
    expect(parseBuildRequest(baseBody({ minSalary: -100 })).ok).toBe(false);
  });

  it("rejects minUnique outside 1-4", () => {
    expect(parseBuildRequest(baseBody({ minUnique: 0 })).ok).toBe(false);
    expect(parseBuildRequest(baseBody({ minUnique: 5 })).ok).toBe(false);
  });

  it("passes through allowPitcherVsHitter as a boolean", () => {
    const result = parseBuildRequest(baseBody({ allowPitcherVsHitter: true }));
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.request.allowPitcherVsHitter).toBe(true);
  });

  it("rejects a non-object body", () => {
    expect(parseBuildRequest(null).ok).toBe(false);
    expect(parseBuildRequest("nope").ok).toBe(false);
    expect(parseBuildRequest(42).ok).toBe(false);
  });

  it("defaults projectionSource to independent when omitted (backward compatible)", () => {
    const result = parseBuildRequest(baseBody());
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.request.projectionSource).toBe("independent");
  });

  it("accepts every real projection source", () => {
    for (const projectionSource of ["independent", "external", "adjusted"]) {
      const result = parseBuildRequest(baseBody({ projectionSource }));
      expect(result.ok).toBe(true);
      if (result.ok) expect(result.request.projectionSource).toBe(projectionSource);
    }
  });

  it("rejects an unknown projectionSource", () => {
    expect(parseBuildRequest(baseBody({ projectionSource: "made_up_source" })).ok).toBe(false);
  });
});
