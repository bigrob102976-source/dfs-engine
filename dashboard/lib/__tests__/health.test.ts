import { describe, expect, it } from "vitest";

import { pipelineStageStatus, qualityReportToRows, ratioHealth } from "../health";

describe("ratioHealth", () => {
  it("is green at or above 95%", () => {
    expect(ratioHealth(95, 100)).toBe("green");
    expect(ratioHealth(198, 198)).toBe("green");
  });

  it("is yellow between 50% and 95%", () => {
    expect(ratioHealth(60, 100)).toBe("yellow");
  });

  it("is red below 50%", () => {
    expect(ratioHealth(10, 100)).toBe("red");
  });

  it("is gray when total is zero (nothing to measure)", () => {
    expect(ratioHealth(0, 0)).toBe("gray");
  });
});

describe("qualityReportToRows", () => {
  it("maps the counts dict into completeness rows with health color", () => {
    const rows = qualityReportToRows({ counts: { xwOBA: 198, Weather: 0 } }, 198);
    expect(rows).toEqual([
      { label: "xwOBA", count: 198, total: 198, color: "green" },
      { label: "Weather", count: 0, total: 198, color: "red" },
    ]);
  });

  it("returns an empty array when the quality report is missing", () => {
    expect(qualityReportToRows(null, 198)).toEqual([]);
    expect(qualityReportToRows(undefined, 198)).toEqual([]);
  });
});

describe("pipelineStageStatus", () => {
  it("is missing when the artifact doesn't exist", () => {
    expect(pipelineStageStatus({ exists: false })).toBe("missing");
  });

  it("is ready when it exists and has no upstream to compare against", () => {
    expect(pipelineStageStatus({ exists: true, generatedAtUtc: "2026-08-11T18:00:00Z" })).toBe("ready");
  });

  it("is ready when generated after its upstream dependency", () => {
    const status = pipelineStageStatus({
      exists: true,
      generatedAtUtc: "2026-08-11T18:10:00Z",
      upstreamGeneratedAtUtc: "2026-08-11T18:00:00Z",
    });
    expect(status).toBe("ready");
  });

  it("is outdated when generated before its upstream dependency", () => {
    const status = pipelineStageStatus({
      exists: true,
      generatedAtUtc: "2026-08-11T17:00:00Z",
      upstreamGeneratedAtUtc: "2026-08-11T18:00:00Z",
    });
    expect(status).toBe("outdated");
  });
});
