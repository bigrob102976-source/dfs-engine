import { describe, expect, it } from "vitest";

import { parseArgs } from "../prepare-next-day";

describe("prepare-next-day.ts parseArgs", () => {
  it("parses --date and defaults --sport to MLB, --throttle-minutes to 25", () => {
    expect(parseArgs(["--date", "2026-09-04"])).toEqual({ date: "2026-09-04", sport: "MLB", throttleMinutes: 25 });
  });

  it("accepts explicit --sport and --throttle-minutes", () => {
    expect(parseArgs(["--date", "2026-09-04", "--sport", "MLB", "--throttle-minutes", "30"])).toEqual({
      date: "2026-09-04", sport: "MLB", throttleMinutes: 30,
    });
  });

  it("throws with a clear usage message when --date is missing", () => {
    expect(() => parseArgs([])).toThrow(/Usage/);
  });
});
