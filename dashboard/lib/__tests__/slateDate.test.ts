import { describe, expect, it } from "vitest";

import { getTodayChicagoDate } from "../currentDate";
import { isValidSlateDateString, resolveSlateDate } from "../slateDate";

describe("isValidSlateDateString", () => {
  it("accepts a real calendar date shaped YYYY-MM-DD", () => {
    expect(isValidSlateDateString("2026-08-21")).toBe(true);
  });

  it("rejects malformed shapes", () => {
    expect(isValidSlateDateString("08-21-2026")).toBe(false);
    expect(isValidSlateDateString("2026/08/21")).toBe(false);
    expect(isValidSlateDateString("2026-8-21")).toBe(false);
    expect(isValidSlateDateString("not-a-date")).toBe(false);
    expect(isValidSlateDateString("")).toBe(false);
  });

  it("rejects a shape-valid but non-existent calendar date", () => {
    expect(isValidSlateDateString("2026-02-30")).toBe(false);
    expect(isValidSlateDateString("2026-13-01")).toBe(false);
    expect(isValidSlateDateString("2026-00-01")).toBe(false);
  });

  it("rejects non-string input", () => {
    expect(isValidSlateDateString(undefined)).toBe(false);
    expect(isValidSlateDateString(null)).toBe(false);
    expect(isValidSlateDateString(20260821)).toBe(false);
  });
});

describe("resolveSlateDate", () => {
  it("falls back to Chicago-today when absent", () => {
    expect(resolveSlateDate(undefined)).toEqual({ ok: true, date: getTodayChicagoDate() });
    expect(resolveSlateDate(null)).toEqual({ ok: true, date: getTodayChicagoDate() });
    expect(resolveSlateDate("")).toEqual({ ok: true, date: getTodayChicagoDate() });
  });

  it("uses a valid explicit date as-is", () => {
    expect(resolveSlateDate("2026-08-21")).toEqual({ ok: true, date: "2026-08-21" });
  });

  it("rejects a present-but-invalid date rather than silently falling back to today", () => {
    const result = resolveSlateDate("not-a-date");
    expect(result).toEqual({ ok: false, error: expect.any(String) });
  });

  it("rejects a shape-valid but non-existent calendar date", () => {
    const result = resolveSlateDate("2026-02-30");
    expect(result.ok).toBe(false);
  });
});
