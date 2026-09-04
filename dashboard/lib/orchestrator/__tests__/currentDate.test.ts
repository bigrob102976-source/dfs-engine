import { describe, expect, it } from "vitest";

import { getTodayEasternDate } from "../../currentDate";

describe("getTodayEasternDate", () => {
  it("stays on the previous Eastern day just before Eastern midnight (EDT, UTC-4 in August)", () => {
    expect(getTodayEasternDate(new Date("2026-08-12T03:30:00Z"))).toBe("2026-08-11");
  });

  it("rolls over right after Eastern local midnight (EDT)", () => {
    expect(getTodayEasternDate(new Date("2026-08-12T04:30:00Z"))).toBe("2026-08-12");
  });

  it("handles the winter EST (UTC-5) offset correctly", () => {
    expect(getTodayEasternDate(new Date("2026-01-15T04:30:00Z"))).toBe("2026-01-14");
    expect(getTodayEasternDate(new Date("2026-01-15T05:30:00Z"))).toBe("2026-01-15");
  });

  it("Central-time wall clock (11 PM CDT, still 1 hour before Eastern midnight) still resolves to the OLD Eastern date", () => {
    // 11:00 PM CDT on Aug 11 == 2026-08-12T04:00:00Z == midnight EDT exactly
    // -- 11:59 PM CDT is one minute before that, i.e. still Aug 11 Eastern.
    expect(getTodayEasternDate(new Date("2026-08-12T03:59:00Z"))).toBe("2026-08-11");
  });

  it("Central-time wall clock just after Eastern midnight already resolves to the NEW Eastern date, even though it's not yet midnight Central", () => {
    // 2026-08-12T04:01:00Z is 11:01 PM CDT (still Aug 11 in Chicago) but
    // 12:01 AM EDT (Aug 12 in Eastern) -- the whole point of this fix.
    expect(getTodayEasternDate(new Date("2026-08-12T04:01:00Z"))).toBe("2026-08-12");
  });

  it("defaults to the current instant when no argument is given", () => {
    const result = getTodayEasternDate();
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("is independent of the server's own system timezone (Railway runs UTC) -- always resolves real Eastern, regardless of process.env.TZ", () => {
    // Intl.DateTimeFormat with an explicit `timeZone` option ignores
    // process.env.TZ entirely (unlike Date's own local-time methods) --
    // this test documents and locks in that guarantee, since it's the
    // whole reason this function is safe to run unmodified on a Railway
    // container (system clock UTC) and produce the same real Eastern
    // date a Central-time browser or any other caller would.
    const originalTz = process.env.TZ;
    try {
      process.env.TZ = "UTC";
      expect(getTodayEasternDate(new Date("2026-08-12T04:30:00Z"))).toBe("2026-08-12");
      process.env.TZ = "America/Chicago";
      expect(getTodayEasternDate(new Date("2026-08-12T04:30:00Z"))).toBe("2026-08-12");
      process.env.TZ = "America/New_York";
      expect(getTodayEasternDate(new Date("2026-08-12T04:30:00Z"))).toBe("2026-08-12");
    } finally {
      process.env.TZ = originalTz;
    }
  });
});
