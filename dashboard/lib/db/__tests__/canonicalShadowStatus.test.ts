import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests, getDb } from "../client";
import { __resetExecutorForTests, getExecutor } from "../executor";
import { easternDateOffset, getTomorrowPrefetchSummary, listShadowSlateStatuses } from "../canonicalShadowStatus";

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
