import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests, getDb } from "../db/client";
import { __resetExecutorForTests } from "../db/executor";
import { canonicalGetSlatePool, canonicalListSlates } from "../servingBackend/canonicalPostgresBackend";

// MLB AUTOMATIC TOMORROW PREP Phase 9 -- proves the actual payoff of
// preparing tomorrow BEFORE Eastern midnight: canonicalListSlates()/
// canonicalGetSlatePool() are ALREADY parameterized by an explicit date
// (unchanged by this milestone) -- once a date's eligibility/
// projections/ownership rows exist, serving that date needs no
// additional wait, no new fetch, and resolves to the exact SAME
// internalSlateId/providerSlateId row that was prepared in advance.
// "Is it midnight yet" is answered entirely by getTodayEasternDate()
// (dashboard/lib/currentDate.ts, already covered by its own existing
// rollover tests, unchanged here) -- this test proves the OTHER half:
// once the caller passes tomorrow's date (whether because a worker
// pre-computed it, or because real Eastern midnight has now passed and
// getTodayEasternDate() returns it), the data is already there.

const TODAY = "2026-09-04";
const TOMORROW = "2026-09-05";

function insertPreparedSlate(internalSlateId: string, providerSlateId: string, slateDate: string) {
  getDb()
    .prepare(
      `INSERT INTO slates (internal_slate_id, sport, site, provider, provider_slate_id, slate_name, slate_date, first_game_start_utc, game_count, schema_version, validation_state, source_provenance, created_at, updated_at)
       VALUES (?, 'MLB', 'draftkings', 'draftkings_unofficial', ?, 'Featured', ?, ?, 9, 'slate_normalized_v1', 'VALID', 'DRAFTKINGS_UNOFFICIAL_LIVE', 'x', 'x')`,
    )
    .run(internalSlateId, providerSlateId, slateDate, `${slateDate}T23:05:00Z`);

  getDb()
    .prepare(
      `INSERT INTO slate_players (internal_slate_id, provider_player_id, name, team, opponent, salary, position_eligibility_json, identity_status, eligibility_status, optimizer_eligible, batting_order, eligibility_computed_at, created_at, updated_at)
       VALUES (?, '1', 'Probable Hitter', 'BOS', 'TOR', 4500, '["OF"]', 'RESOLVED', 'PROBABLE_HITTER', 1, 3, ?, 'x', 'x')`,
    )
    .run(internalSlateId, new Date().toISOString());

  getDb()
    .prepare(
      `INSERT INTO canonical_slate_player_projections (id, internal_slate_id, provider_player_id, source, model_version, projection, ceiling, floor, generated_at, created_at, updated_at)
       VALUES (?, ?, '1', 'native', '1.0.0', 11.5, 18.0, 4.0, ?, 'x', 'x')`,
    )
    .run(`proj-${internalSlateId}`, internalSlateId, new Date().toISOString());

  getDb()
    .prepare(
      `INSERT INTO canonical_slate_player_ownership (id, internal_slate_id, provider_player_id, model_version, projected_ownership, ownership_tier, leverage_score, chalk_score, generated_at, created_at, updated_at)
       VALUES (?, ?, '1', '0.1.0', 22.5, 'balanced', 0.0, 55, ?, 'x', 'x')`,
    )
    .run(`own-${internalSlateId}`, internalSlateId, new Date().toISOString());
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

describe("MLB AUTOMATIC TOMORROW PREP Phase 9 -- midnight rollover serving", () => {
  it("a slate prepared for tomorrow is invisible under today's own date query (never leaks early)", async () => {
    insertPreparedSlate("s-tomorrow", "153153", TOMORROW);
    const todayResult = await canonicalListSlates(TODAY);
    expect(todayResult.status).toBe("no_slate");
  });

  it("the SAME already-prepared slate becomes immediately servable once queried under its own date -- no post-midnight wait, no new fetch", async () => {
    insertPreparedSlate("s-tomorrow", "153153", TOMORROW);

    const result = await canonicalListSlates(TOMORROW);
    expect(result.status).toBe("ready");
    expect(result.slates).toHaveLength(1);
    expect(result.slates[0].slateId).toBe("153153"); // same providerSlateId, no re-derivation

    const pool = await canonicalGetSlatePool(TOMORROW, "153153", "MLB");
    const eligible = pool.players.filter((p) => p.optimizerEligible);
    expect(eligible).toHaveLength(1);
    expect(eligible[0].eligibilityStatus).toBe("PROBABLE_HITTER");
    expect(eligible[0].projection).toBe(11.5); // real, already-computed projection -- no wait
    expect(eligible[0].ownership).toBe(22.5); // real, already-computed ownership -- no wait
    expect(pool.hasNativeProjections).toBe(true);
    expect(pool.hasOwnership).toBe(true);
  });

  it("today and tomorrow can be independently prepared and served without collision -- distinct rows, distinct data", async () => {
    insertPreparedSlate("s-today", "152904", TODAY);
    insertPreparedSlate("s-tomorrow", "153153", TOMORROW);

    const today = await canonicalListSlates(TODAY);
    const tomorrow = await canonicalListSlates(TOMORROW);
    expect(today.slates.map((s) => s.slateId)).toEqual(["152904"]);
    expect(tomorrow.slates.map((s) => s.slateId)).toEqual(["153153"]);

    // internalSlateId identity is preserved end to end -- verifiable via
    // direct row lookup, never re-minted between "prep" and "serve".
    const row = getDb().prepare("SELECT internal_slate_id FROM slates WHERE provider_slate_id = '153153'").get() as { internal_slate_id: string };
    expect(row.internal_slate_id).toBe("s-tomorrow");
  });
});
