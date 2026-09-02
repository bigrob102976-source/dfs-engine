import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests, getDb } from "../client";
import { __resetExecutorForTests, getExecutor } from "../executor";
import { easternDateOffset, getEligibilitySummariesBySlate, getTomorrowPrefetchSummary, listShadowSlateStatuses } from "../canonicalShadowStatus";

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

function insertSlate(overrides: Partial<{
  internal_slate_id: string; provider_slate_id: string; slate_date: string; validation_state: string;
}> = {}) {
  const row = {
    internal_slate_id: "s1", provider_slate_id: "152904", slate_date: "2026-08-31", validation_state: "VALID",
    ...overrides,
  };
  getDb()
    .prepare(
      `INSERT INTO slates (internal_slate_id, sport, site, provider, provider_slate_id, slate_name, slate_date, first_game_start_utc, schema_version, validation_state, created_at, updated_at)
       VALUES (?, 'MLB', 'draftkings', 'draftkings_unofficial', ?, 'Main', ?, ?, 'slate_normalized_v1', ?, 'x', 'x')`,
    )
    .run(row.internal_slate_id, row.provider_slate_id, row.slate_date, `${row.slate_date}T23:05:00Z`, row.validation_state);
}

describe("M4H: easternDateOffset", () => {
  it("day 0 and day 1 are always exactly one calendar day apart", () => {
    const today = easternDateOffset(0);
    const tomorrow = easternDateOffset(1);
    const todayMs = Date.parse(`${today}T12:00:00Z`);
    const tomorrowMs = Date.parse(`${tomorrow}T12:00:00Z`);
    expect(tomorrowMs - todayMs).toBe(24 * 60 * 60 * 1000);
  });
});

describe("M4H: listShadowSlateStatuses prefetchState", () => {
  it("classifies a row dated today as TODAY_CURRENT", async () => {
    const db = getExecutor();
    const today = easternDateOffset(0);
    insertSlate({ slate_date: today });
    const rows = await listShadowSlateStatuses();
    expect(rows[0].prefetchState).toBe("TODAY_CURRENT");
  });

  it("classifies a row dated tomorrow as FUTURE_PREFETCHED", async () => {
    const tomorrow = easternDateOffset(1);
    insertSlate({ slate_date: tomorrow });
    const rows = await listShadowSlateStatuses();
    expect(rows[0].prefetchState).toBe("FUTURE_PREFETCHED");
  });

  it("classifies a row dated yesterday as PAST", async () => {
    const yesterday = easternDateOffset(-1);
    insertSlate({ slate_date: yesterday });
    const rows = await listShadowSlateStatuses();
    expect(rows[0].prefetchState).toBe("PAST");
  });
});

describe("M4H/M4L: getTomorrowPrefetchSummary", () => {
  it("reports NOT_YET_PUBLISHED honestly when no row exists for tomorrow -- no fake slate", async () => {
    insertSlate({ slate_date: easternDateOffset(0) }); // only today's row exists
    const summary = await getTomorrowPrefetchSummary();
    expect(summary.status).toBe("NOT_YET_PUBLISHED");
    expect(summary.date).toBe(easternDateOffset(1));
    expect(summary.slates).toEqual([]);
  });

  it("reports FUTURE_PREFETCHED with the real row(s) once tomorrow has been prefetched", async () => {
    const tomorrow = easternDateOffset(1);
    insertSlate({ internal_slate_id: "s1", provider_slate_id: "1", slate_date: tomorrow });
    insertSlate({ internal_slate_id: "s2", provider_slate_id: "2", slate_date: tomorrow });
    insertSlate({ internal_slate_id: "s3", provider_slate_id: "3", slate_date: easternDateOffset(0) }); // today's own row must not leak in

    const summary = await getTomorrowPrefetchSummary();
    expect(summary.status).toBe("FUTURE_PREFETCHED");
    expect(summary.slates.map((s) => s.internal_slate_id).sort()).toEqual(["s1", "s2"]);
  });
});

function insertPlayer(overrides: Partial<{ internal_slate_id: string; provider_player_id: string; eligibility_status: string | null; optimizer_eligible: number; eligibility_computed_at: string | null }> = {}) {
  const row = {
    internal_slate_id: "s1", provider_player_id: "1", eligibility_status: null, optimizer_eligible: 0, eligibility_computed_at: null,
    ...overrides,
  };
  getDb()
    .prepare(
      `INSERT INTO slate_players (internal_slate_id, provider_player_id, name, team, opponent, salary, position_eligibility_json, identity_status, eligibility_status, optimizer_eligible, eligibility_computed_at, created_at, updated_at)
       VALUES (?, ?, 'Player', 'BOS', 'TOR', 4500, '["OF"]', 'UNRESOLVED', ?, ?, ?, 'x', 'x')`,
    )
    .run(row.internal_slate_id, row.provider_player_id, row.eligibility_status, row.optimizer_eligible, row.eligibility_computed_at);
}

describe("M7K: eligibility observability", () => {
  it("getEligibilitySummariesBySlate aggregates eligible/unconfirmed/unmatched counts and the latest computed_at per slate", async () => {
    insertSlate({ internal_slate_id: "s1" });
    insertPlayer({ provider_player_id: "1", eligibility_status: "STARTING_HITTER", optimizer_eligible: 1, eligibility_computed_at: "2026-08-31T10:00:00Z" });
    insertPlayer({ provider_player_id: "2", eligibility_status: "LINEUP_UNCONFIRMED", optimizer_eligible: 0, eligibility_computed_at: "2026-08-31T10:00:00Z" });
    insertPlayer({ provider_player_id: "3", eligibility_status: "UNMATCHED", optimizer_eligible: 0, eligibility_computed_at: "2026-08-31T11:00:00Z" });
    insertPlayer({ provider_player_id: "4" }); // never computed at all -- honest "unconfirmed", not "unmatched"

    const summaries = await getEligibilitySummariesBySlate();
    const s1 = summaries.get("s1")!;
    expect(s1.totalPlayers).toBe(4);
    expect(s1.eligibleCount).toBe(1);
    expect(s1.unconfirmedCount).toBe(2); // LINEUP_UNCONFIRMED + never-computed
    expect(s1.unmatchedCount).toBe(1);
    expect(s1.lastComputedAt).toBe("2026-08-31T11:00:00Z");
  });

  it("listShadowSlateStatuses wires the real eligibility summary onto each slate row, and null when a slate has zero players", async () => {
    insertSlate({ internal_slate_id: "s1" });
    insertPlayer({ provider_player_id: "1", eligibility_status: "STARTING_HITTER", optimizer_eligible: 1 });
    insertSlate({ internal_slate_id: "s2", provider_slate_id: "2" }); // zero players promoted yet

    const rows = await listShadowSlateStatuses();
    const s1 = rows.find((r) => r.internal_slate_id === "s1")!;
    const s2 = rows.find((r) => r.internal_slate_id === "s2")!;
    expect(s1.eligibility).toEqual(expect.objectContaining({ totalPlayers: 1, eligibleCount: 1 }));
    expect(s2.eligibility).toBeNull();
  });
});
