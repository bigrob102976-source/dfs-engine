import { afterEach, describe, expect, it, vi } from "vitest";

import { effectiveGameIds, filterByGameIdField, filterByGameIds, formatSlateLabel, resolveSlateContext } from "../slateContext";
import type { SlateOption } from "../orchestrator/types";

vi.mock("../optimizerWorkspace/poolCache", () => ({
  listSlates: vi.fn(),
}));

afterEach(() => {
  vi.clearAllMocks();
});

function slate(overrides: Partial<SlateOption> = {}): SlateOption {
  return { slateId: "main", slateName: "Main", gameCount: 9, startTime: null, gameIds: ["g1", "g2"], playerCount: 100, ...overrides };
}

describe("resolveSlateContext", () => {
  it("never auto-selects a slate when no slate is requested (full-day default)", async () => {
    const { listSlates } = await import("../optimizerWorkspace/poolCache");
    vi.mocked(listSlates).mockResolvedValue({
      status: "ready", reason: null, providerName: "draftkings_csv", providerType: "real", isMock: false,
      isConnected: true, source: "real_dk_csv", slates: [slate()], slatesAvailable: 1,
    });

    const ctx = await resolveSlateContext("2026-08-17");
    expect(ctx.selected).toBeNull();
    expect(ctx.slates).toHaveLength(1);
  });

  it("selects the requested slate when it matches", async () => {
    const { listSlates } = await import("../optimizerWorkspace/poolCache");
    const turbo = slate({ slateId: "turbo", slateName: "Turbo", gameIds: ["g3"] });
    vi.mocked(listSlates).mockResolvedValue({
      status: "ready", reason: null, providerName: "draftkings_csv", providerType: "real", isMock: false,
      isConnected: true, source: "real_dk_csv", slates: [slate(), turbo], slatesAvailable: 2,
    });

    const ctx = await resolveSlateContext("2026-08-17", "turbo");
    expect(ctx.selected?.slateId).toBe("turbo");
  });

  it("returns null selected (not an error) when the requested slate id doesn't exist", async () => {
    const { listSlates } = await import("../optimizerWorkspace/poolCache");
    vi.mocked(listSlates).mockResolvedValue({
      status: "ready", reason: null, providerName: "draftkings_csv", providerType: "real", isMock: false,
      isConnected: true, source: "real_dk_csv", slates: [slate()], slatesAvailable: 1,
    });

    const ctx = await resolveSlateContext("2026-08-17", "does-not-exist");
    expect(ctx.selected).toBeNull();
  });

  it("flags gameIdsUnavailable when the selected slate has no resolved game_ids", async () => {
    const { listSlates } = await import("../optimizerWorkspace/poolCache");
    vi.mocked(listSlates).mockResolvedValue({
      status: "ready", reason: null, providerName: "draftkings_csv", providerType: "real", isMock: false,
      isConnected: true, source: "real_dk_csv", slates: [slate({ gameIds: [] })], slatesAvailable: 1,
    });

    const ctx = await resolveSlateContext("2026-08-17", "main");
    expect(ctx.selected).not.toBeNull();
    expect(ctx.gameIdsUnavailable).toBe(true);
  });
});

describe("effectiveGameIds / filterByGameIds / filterByGameIdField", () => {
  it("returns null (no filtering) when no slate is selected", () => {
    expect(effectiveGameIds({ selected: null })).toBeNull();
  });

  it("returns null when the selected slate's game_ids are unresolved (never filters to zero)", () => {
    expect(effectiveGameIds({ selected: slate({ gameIds: [] }) })).toBeNull();
  });

  it("returns the slate's game_ids when resolved", () => {
    expect(effectiveGameIds({ selected: slate({ gameIds: ["g1", "g2"] }) })).toEqual(["g1", "g2"]);
  });

  it("filterByGameIds passes everything through when gameIds is null", () => {
    const rows = [{ gameId: "g1" }, { gameId: "g9" }, { gameId: null }];
    expect(filterByGameIds(rows, null)).toEqual(rows);
  });

  it("filterByGameIds keeps only rows whose gameId is in the slate, dropping null-gameId rows", () => {
    const rows = [{ gameId: "g1" }, { gameId: "g9" }, { gameId: null }];
    expect(filterByGameIds(rows, ["g1"])).toEqual([{ gameId: "g1" }]);
  });

  it("no cross-slate leakage: a player from a game excluded from the slate never appears", () => {
    const rows = [{ gameId: "g-main" }, { gameId: "g-turbo" }];
    expect(filterByGameIds(rows, ["g-main"])).toEqual([{ gameId: "g-main" }]);
    expect(filterByGameIds(rows, ["g-turbo"])).toEqual([{ gameId: "g-turbo" }]);
  });

  it("filterByGameIdField mirrors filterByGameIds for game_id-keyed records", () => {
    const games = [{ game_id: "g1" }, { game_id: "g2" }];
    expect(filterByGameIdField(games, ["g1"])).toEqual([{ game_id: "g1" }]);
    expect(filterByGameIdField(games, null)).toEqual(games);
  });
});

describe("formatSlateLabel", () => {
  it("includes game count when known", () => {
    expect(formatSlateLabel(slate({ slateName: "Main", gameCount: 9 }))).toBe("Main — 9 Games");
  });

  it("uses singular Game for a 1-game slate", () => {
    expect(formatSlateLabel(slate({ slateName: "Late", gameCount: 1 }))).toBe("Late — 1 Game");
  });

  it("falls back to slateId when slateName is null, and omits game count when unknown", () => {
    expect(formatSlateLabel(slate({ slateId: "dkcsv-x-2026-08-17", slateName: null, gameCount: null }))).toBe("dkcsv-x-2026-08-17");
  });
});
