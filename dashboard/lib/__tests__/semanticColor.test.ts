import { describe, expect, it } from "vitest";

import { normalizedScoreTone, percentileTone, toneLabel, weatherRiskTone } from "../semanticColor";

describe("normalizedScoreTone -- HIGH_GOOD", () => {
  it("returns null for missing data instead of guessing a color", () => {
    expect(normalizedScoreTone(null, "HIGH_GOOD")).toBeNull();
  });

  it("high confidence/data-quality/power/matchup -> GREEN", () => {
    expect(normalizedScoreTone(85, "HIGH_GOOD")?.tone).toBe("green");
    expect(normalizedScoreTone(70, "HIGH_GOOD")?.tone).toBe("green");
  });

  it("moderate -> YELLOW", () => {
    expect(normalizedScoreTone(55, "HIGH_GOOD")?.tone).toBe("yellow");
    expect(normalizedScoreTone(40, "HIGH_GOOD")?.tone).toBe("yellow");
  });

  it("low -> RED", () => {
    expect(normalizedScoreTone(20, "HIGH_GOOD")?.tone).toBe("red");
    expect(normalizedScoreTone(39.99, "HIGH_GOOD")?.tone).toBe("red");
  });
});

describe("normalizedScoreTone -- LOW_GOOD (Risk)", () => {
  it("low risk -> GREEN", () => {
    expect(normalizedScoreTone(10, "LOW_GOOD")?.tone).toBe("green");
    expect(normalizedScoreTone(29.99, "LOW_GOOD")?.tone).toBe("green");
  });

  it("moderate risk -> YELLOW", () => {
    expect(normalizedScoreTone(45, "LOW_GOOD")?.tone).toBe("yellow");
  });

  it("high risk -> RED", () => {
    expect(normalizedScoreTone(80, "LOW_GOOD")?.tone).toBe("red");
    expect(normalizedScoreTone(60, "LOW_GOOD")?.tone).toBe("red");
  });

  it("never maps a high number to green just because it's high -- direction always governs", () => {
    // A high RISK number is BAD -- must be red, the opposite of a high
    // HIGH_GOOD number (which is green). This is the exact bug class
    // Part 7 exists to prevent.
    expect(normalizedScoreTone(90, "LOW_GOOD")?.tone).toBe("red");
    expect(normalizedScoreTone(90, "HIGH_GOOD")?.tone).toBe("green");
  });
});

describe("weatherRiskTone", () => {
  it("matches the documented GREEN 0-29.99 / YELLOW 30-59.99 / RED 60-100 bands", () => {
    expect(weatherRiskTone(0)?.tone).toBe("green");
    expect(weatherRiskTone(12)?.tone).toBe("green");
    expect(weatherRiskTone(29.99)?.tone).toBe("green");
    expect(weatherRiskTone(30)?.tone).toBe("yellow");
    expect(weatherRiskTone(48)?.tone).toBe("yellow");
    expect(weatherRiskTone(59.99)?.tone).toBe("yellow");
    expect(weatherRiskTone(60)?.tone).toBe("red");
    expect(weatherRiskTone(82)?.tone).toBe("red");
  });

  it("returns null for missing data", () => {
    expect(weatherRiskTone(null)).toBeNull();
  });
});

describe("percentileTone -- raw/unbounded slate-relative values (Game Total, Team Implied Runs)", () => {
  it("high total in a HIGH_GOOD context (hitting environment / stack) -> GREEN", () => {
    const totals = [7.0, 8.0, 9.0, 10.0, 11.0];
    expect(percentileTone(11.0, totals, "HIGH_GOOD").tone).toBe("green");
  });

  it("middle total -> YELLOW", () => {
    const totals = [7.0, 8.0, 9.0, 10.0, 11.0];
    expect(percentileTone(9.0, totals, "HIGH_GOOD").tone).toBe("yellow");
  });

  it("low total -> RED -- this is the confirmed bug fix: high=GREEN, low=RED for a hitting environment", () => {
    const totals = [7.0, 8.0, 9.0, 10.0, 11.0];
    expect(percentileTone(7.0, totals, "HIGH_GOOD").tone).toBe("red");
  });

  it("reverses for a LOW_GOOD raw metric (e.g. a pitcher's opponent implied total) -- same numbers, opposite color", () => {
    const totals = [7.0, 8.0, 9.0, 10.0, 11.0];
    expect(percentileTone(11.0, totals, "LOW_GOOD").tone).toBe("red");
    expect(percentileTone(7.0, totals, "LOW_GOOD").tone).toBe("green");
  });
});

describe("toneLabel -- accessibility: color is never the only signal", () => {
  it("provides a text label for every tone", () => {
    expect(toneLabel("green")).toBe("GOOD");
    expect(toneLabel("yellow")).toBe("CAUTION");
    expect(toneLabel("red")).toBe("BAD");
  });
});
