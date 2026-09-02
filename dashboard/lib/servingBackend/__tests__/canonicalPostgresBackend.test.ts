import fs from "node:fs";
import path from "node:path";
import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests, getDb } from "../../db/client";
import { __resetExecutorForTests } from "../../db/executor";
import { canonicalGetSlatePool, canonicalListSlates } from "../canonicalPostgresBackend";

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

function insertSlate(overrides: Partial<{
  internal_slate_id: string; provider_slate_id: string; slate_date: string; validation_state: string;
  promoted_at: string | null; game_count: number | null; salary_cap: number | null; slate_name: string;
}> = {}) {
  const row = {
    internal_slate_id: "s1", provider_slate_id: "dkunofficial-152904", slate_date: "2026-08-31", validation_state: "VALID",
    promoted_at: new Date().toISOString(), game_count: 8, salary_cap: 50000, slate_name: "Main",
    ...overrides,
  };
  getDb()
    .prepare(
      `INSERT INTO slates (
         internal_slate_id, sport, site, provider, provider_slate_id, slate_name, slate_date, first_game_start_utc,
         game_count, game_ids_json, salary_cap, schema_version, validation_state, source_provenance,
         promoted_at, player_count, created_at, updated_at
       ) VALUES (?, 'MLB', 'draftkings', 'draftkings_unofficial', ?, ?, ?, '2026-08-31T23:05:00Z', ?, '[]', ?, 'slate_normalized_v1', ?, 'DRAFTKINGS_UNOFFICIAL_LIVE', ?, 1, 'x', 'x')`,
    )
    .run(row.internal_slate_id, row.provider_slate_id, row.slate_name, row.slate_date, row.game_count, row.salary_cap, row.validation_state, row.promoted_at);
  return row;
}

function insertPlayer(overrides: Partial<{
  internal_slate_id: string; provider_player_id: string; internal_player_id: string | null;
  name: string; team: string; opponent: string | null; game_id: string | null; salary: number;
  position_eligibility_json: string; identity_status: string;
}> = {}) {
  const row = {
    internal_slate_id: "s1", provider_player_id: "999", internal_player_id: null,
    name: "Flex Player", team: "BOS", opponent: "TOR", game_id: null, salary: 4500,
    position_eligibility_json: JSON.stringify(["OF"]), identity_status: "UNRESOLVED",
    ...overrides,
  };
  getDb()
    .prepare(
      `INSERT INTO slate_players (
         internal_slate_id, provider_player_id, internal_player_id, name, team, opponent, game_id, salary,
         position_eligibility_json, identity_status, created_at, updated_at
       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'x', 'x')`,
    )
    .run(
      row.internal_slate_id, row.provider_player_id, row.internal_player_id, row.name, row.team, row.opponent,
      row.game_id, row.salary, row.position_eligibility_json, row.identity_status,
    );
  return row;
}

function insertResolvedPlayer(internalPlayerId: string, mlbExternalId: string) {
  getDb()
    .prepare("INSERT INTO players (internal_player_id, sport, canonical_name, normalized_name, active, created_at, updated_at) VALUES (?, 'MLB', 'A', 'a', 1, 'x', 'x')")
    .run(internalPlayerId);
  getDb()
    .prepare(
      `INSERT INTO player_external_ids (id, internal_player_id, sport, provider, external_id, external_id_type, match_method, match_confidence, is_current, valid_from, created_at, updated_at)
       VALUES (?, ?, 'MLB', 'mlbam', ?, 'mlbam_id', 'exact_deterministic_source_mapping', 1.0, 1, 'x', 'x', 'x')`,
    )
    .run(`ext-${internalPlayerId}`, internalPlayerId, mlbExternalId);
}

describe("M5B: canonicalListSlates", () => {
  it("reports no_slate honestly when nothing has been promoted for this date", async () => {
    const result = await canonicalListSlates("2026-08-31");
    expect(result.status).toBe("no_slate");
    expect(result.slates).toEqual([]);
    expect(result.isMock).toBe(false);
  });

  it("lists a VALID promoted slate, mapped to SlateOption", async () => {
    insertSlate();
    const result = await canonicalListSlates("2026-08-31");
    expect(result.status).toBe("ready");
    expect(result.isMock).toBe(false);
    expect(result.source).toBe("draftkings_unofficial_live");
    expect(result.slates).toEqual([
      { slateId: "dkunofficial-152904", slateName: "Main", gameCount: 8, startTime: "2026-08-31T23:05:00Z", gameIds: [], playerCount: 1 },
    ]);
    expect(result.dataStatus).toBe("fresh");
  });

  it("excludes a REJECTED slate -- only VALID, promoted data is ever served", async () => {
    insertSlate({ validation_state: "REJECTED" });
    const result = await canonicalListSlates("2026-08-31");
    expect(result.status).toBe("no_slate");
  });

  it("reports stale (not fresh) for a slate promoted well outside the fresh window but still within the reuse ceiling", async () => {
    insertSlate({ promoted_at: new Date(Date.now() - 45 * 60 * 1000).toISOString() }); // 45 min old
    const result = await canonicalListSlates("2026-08-31");
    expect(result.status).toBe("ready");
    expect(result.dataStatus).toBe("stale");
  });

  it("refuses to serve (stale_expired) data promoted too long ago -- never a live DK call, never fake data", async () => {
    insertSlate({ promoted_at: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString() }); // 3h old
    const result = await canonicalListSlates("2026-08-31");
    expect(result.status).toBe("stale_expired");
    expect(result.slates).toEqual([]);
  });

  it("M5G: a slate promoted for a FUTURE date never appears in today's list", async () => {
    insertSlate({ internal_slate_id: "future-1", provider_slate_id: "dkunofficial-999", slate_date: "2026-09-01" });
    const result = await canonicalListSlates("2026-08-31");
    expect(result.status).toBe("no_slate");
  });

  it("M5H: day-rollover simulation -- the SAME row (same internalSlateId/providerSlateId) hidden as tomorrow becomes today's servable slate once its own slateDate is queried, with no duplicate row minted", async () => {
    insertSlate({ internal_slate_id: "rollover-1", provider_slate_id: "dkunofficial-rollover", slate_date: "2026-09-01" });

    const beforeRollover = await canonicalListSlates("2026-08-31"); // "today" is still Aug 31
    expect(beforeRollover.status).toBe("no_slate"); // hidden -- see M5G above

    const afterRollover = await canonicalListSlates("2026-09-01"); // Eastern midnight has now passed
    expect(afterRollover.status).toBe("ready");
    expect(afterRollover.slates).toEqual([
      { slateId: "dkunofficial-rollover", slateName: "Main", gameCount: 8, startTime: "2026-08-31T23:05:00Z", gameIds: [], playerCount: 1 },
    ]);

    const rows = getDb().prepare("SELECT COUNT(*) as c FROM slates WHERE provider_slate_id = 'dkunofficial-rollover'").get() as { c: number };
    expect(rows.c).toBe(1); // never duplicated -- the same row simply became eligible once its own date matched the query
  });
});

describe("M5B: canonicalGetSlatePool", () => {
  it("throws a clear error when the slate is absent -- never fabricates a pool", async () => {
    await expect(canonicalGetSlatePool("2026-08-31", "dkunofficial-152904")).rejects.toThrow(/not found/);
  });

  it("builds a real pool from slate_players, resolving mlbPlayerId only for RESOLVED identities", async () => {
    insertSlate();
    insertResolvedPlayer("ip-1", "660271");
    insertPlayer({ provider_player_id: "1", internal_player_id: "ip-1", identity_status: "RESOLVED", position_eligibility_json: JSON.stringify(["P"]) });
    insertPlayer({ provider_player_id: "2", internal_player_id: null, identity_status: "UNRESOLVED", position_eligibility_json: JSON.stringify(["OF"]) });

    const pool = await canonicalGetSlatePool("2026-08-31", "dkunofficial-152904");
    expect(pool.players).toHaveLength(2);

    const pitcher = pool.players.find((p) => p.dkPlayerId === "1")!;
    expect(pitcher.mlbPlayerId).toBe("660271");
    expect(pitcher.playerType).toBe("pitcher");
    expect(pitcher.matchStatus).toBe("matched");
    expect(pitcher.optimizerEligible).toBe(true);
    expect(pitcher.eligibilityStatus).toBe("CANONICAL_UNCONFIRMED");
    // Honest absence -- never fabricated projection/ownership data.
    expect(pitcher.projection).toBeNull();
    expect(pitcher.ownership).toBeNull();

    const unresolved = pool.players.find((p) => p.dkPlayerId === "2")!;
    expect(unresolved.mlbPlayerId).toBeNull();
    expect(unresolved.matchStatus).toBe("unmatched");
    expect(unresolved.playerType).toBe("hitter");
    // Unresolved identity is still fully servable -- never blocks the slate.
    expect(unresolved.optimizerEligible).toBe(true);

    expect(pool.pitcherCount).toBe(1);
    expect(pool.hitterCount).toBe(1);
    expect(pool.unmatchedCount).toBe(1);
    expect(pool.hasOwnership).toBe(false);
    expect(pool.hasAiProjections).toBe(false);
    expect(pool.salaryCap).toBe(50000);
  });

  it("refuses to serve pool data that has aged past the safe reuse ceiling", async () => {
    insertSlate({ promoted_at: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString() });
    insertPlayer();
    await expect(canonicalGetSlatePool("2026-08-31", "dkunofficial-152904")).rejects.toThrow(/too old to use safely/);
  });

  it("REJECTED validation state is never servable even if rows exist", async () => {
    insertSlate({ validation_state: "REJECTED" });
    insertPlayer();
    await expect(canonicalGetSlatePool("2026-08-31", "dkunofficial-152904")).rejects.toThrow(/not found/);
  });
});

describe("M5K: canonical backend makes zero DraftKings network calls (structural)", () => {
  it("canonicalPostgresBackend.ts never imports a network/subprocess-capable module", () => {
    const src = fs.readFileSync(path.join(__dirname, "..", "canonicalPostgresBackend.ts"), "utf8");
    const importLines = src.split("\n").filter((line) => line.trimStart().startsWith("import "));
    const importBlock = importLines.join("\n");
    for (const forbidden of ["draftkings_unofficial", "runPythonScript", "fetch_dfs_slate", "list_dfs_slates", "node:child_process", "node:http", "node:https"]) {
      expect(importBlock).not.toContain(forbidden);
    }
  });
});
