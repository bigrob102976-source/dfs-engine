import { describe, expect, it } from "vitest";

import { fmt, fmtPercent, fmtSalary, fmtValue, identityLabel, projectionLabel } from "./format";

describe("fmt", () => {
  it("renders null as --, never 0 or the string null", () => {
    expect(fmt(null)).toBe("--");
    expect(fmt(undefined)).toBe("--");
    expect(fmt(Number.NaN)).toBe("--");
  });

  it("renders a real zero as 0.0, distinct from missing", () => {
    expect(fmt(0)).toBe("0.0");
  });

  it("formats a real number to the requested precision", () => {
    expect(fmt(12.345, 2)).toBe("12.35");
  });
});

describe("fmtSalary / fmtPercent / fmtValue", () => {
  it("fmtSalary renders -- for null, real formatted dollars otherwise", () => {
    expect(fmtSalary(null)).toBe("--");
    expect(fmtSalary(6000)).toBe("$6,000");
  });

  it("fmtPercent renders -- for null, never a fake 0%", () => {
    expect(fmtPercent(null)).toBe("--");
    expect(fmtPercent(0.42)).toBe("42%");
  });

  it("fmtValue renders -- when projection is null even if salary is real", () => {
    expect(fmtValue(null, 6000)).toBe("--");
    expect(fmtValue(12, 6000)).toBe("2.00");
  });
});

describe("identityLabel", () => {
  it("labels an unresolved offensive player explicitly, never blank", () => {
    expect(identityLabel({ is_team_entity: false, identity_resolved: false })).toBe("Identity Unresolved");
  });
  it("labels a resolved offensive player as Resolved", () => {
    expect(identityLabel({ is_team_entity: false, identity_resolved: true })).toBe("Resolved");
  });
  it("labels DST as Team (never a fake GSIS identity)", () => {
    expect(identityLabel({ is_team_entity: true, identity_resolved: false })).toBe("Team");
  });
});

describe("projectionLabel", () => {
  it("labels a missing projection honestly, never blank", () => {
    expect(projectionLabel(null)).toBe("No Projection");
    expect(projectionLabel(undefined)).toBe("No Projection");
  });
  it("labels the real learned model source", () => {
    expect(projectionLabel("BIG_MONEY_NATIVE")).toBe("BIG MONEY NATIVE");
  });
  it("labels a DST baseline fallback distinctly -- never identical to a learned model", () => {
    const label = projectionLabel("BIG_MONEY_NATIVE_DST_BASELINE");
    expect(label).toBe("BIG MONEY NATIVE DST BASELINE");
    expect(label).not.toBe(projectionLabel("BIG_MONEY_NATIVE"));
  });
});
