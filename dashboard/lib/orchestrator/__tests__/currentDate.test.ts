import { describe, expect, it } from "vitest";

import { getTodayChicagoDate } from "../../currentDate";

describe("getTodayChicagoDate", () => {
  it("stays on the previous Chicago day just after UTC midnight (CDT, UTC-5 in August)", () => {
    expect(getTodayChicagoDate(new Date("2026-08-12T04:30:00Z"))).toBe("2026-08-11");
  });

  it("rolls over after Chicago local midnight (CDT)", () => {
    expect(getTodayChicagoDate(new Date("2026-08-12T06:00:00Z"))).toBe("2026-08-12");
  });

  it("handles the winter CST (UTC-6) offset correctly", () => {
    expect(getTodayChicagoDate(new Date("2026-01-15T05:30:00Z"))).toBe("2026-01-14");
    expect(getTodayChicagoDate(new Date("2026-01-15T07:00:00Z"))).toBe("2026-01-15");
  });

  it("defaults to the current instant when no argument is given", () => {
    const result = getTodayChicagoDate();
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
