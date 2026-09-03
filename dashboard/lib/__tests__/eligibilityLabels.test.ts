import { describe, expect, it } from "vitest";

import { formatEligibilityStatus } from "../eligibilityLabels";

// PROBABLE FIX milestone: never show a probable starter as confirmed,
// and never show a confirmed starter as merely probable -- the
// distinction the milestone explicitly requires be preserved end to end.
describe("formatEligibilityStatus", () => {
  it("labels a confirmed hitter as Confirmed Starter", () => {
    expect(formatEligibilityStatus("STARTING_HITTER", "CONFIRMED")).toEqual({ label: "Confirmed Starter", tone: "starting" });
  });

  it("labels a probable hitter as Probable Starter, distinct tone from confirmed", () => {
    const result = formatEligibilityStatus("PROBABLE_HITTER", "PROBABLE");
    expect(result.label).toBe("Probable Starter");
    expect(result.tone).toBe("probable");
    expect(result.tone).not.toBe("starting");
  });

  it("labels a confirmed pitcher as Confirmed Starter", () => {
    expect(formatEligibilityStatus("STARTING_PITCHER", "CONFIRMED")).toEqual({ label: "Confirmed Starter", tone: "starting" });
  });

  it("labels a probable (not-yet-confirmed) pitcher as Probable Starter", () => {
    const result = formatEligibilityStatus("STARTING_PITCHER", "PROBABLE");
    expect(result.label).toBe("Probable Starter");
    expect(result.tone).toBe("probable");
  });

  it("falls back to a starting label for a pitcher with no confirmation info at all", () => {
    expect(formatEligibilityStatus("STARTING_PITCHER")).toEqual({ label: "Starting Pitcher", tone: "starting" });
  });

  it("labels BENCH/RELIEF/OUT/LINEUP_UNCONFIRMED per the milestone's own vocabulary", () => {
    expect(formatEligibilityStatus("BENCH").label).toBe("Bench");
    expect(formatEligibilityStatus("RELIEF_PITCHER").label).toBe("Relief");
    expect(formatEligibilityStatus("OUT").label).toBe("Out");
    expect(formatEligibilityStatus("LINEUP_UNCONFIRMED").label).toBe("Unknown");
  });

  it("never fabricates a status for a null (not-yet-computed) row", () => {
    expect(formatEligibilityStatus(null)).toEqual({ label: "Not Computed", tone: "unconfirmed" });
  });

  it("falls back gracefully for an unrecognized status string", () => {
    expect(formatEligibilityStatus("SOME_FUTURE_STATUS")).toEqual({ label: "SOME_FUTURE_STATUS", tone: "unresolved" });
  });
});
