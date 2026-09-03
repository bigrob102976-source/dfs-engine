import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests, getDb } from "../client";
import { __resetExecutorForTests } from "../executor";
import { __resetStorageForTests } from "../../storage/getStorage";
import { computeAndPersistNativeProjectionsForSlate, getCanonicalProjectionsForSlate, refreshCanonicalProjectionsForDate } from "../canonicalProjections";

let tmpDir: string;

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

function insertSlate(overrides: Partial<{ internal_slate_id: string; slate_date: string; provider_slate_id: string }> = {}) {
  const row = { internal_slate_id: "s1", slate_date: "2026-08-31", provider_slate_id: "dkunofficial-1", ...overrides };
  getDb()
    .prepare(
      `INSERT INTO slates (
         internal_slate_id, sport, site, provider, provider_slate_id, slate_name, slate_date, first_game_start_utc,
         schema_version, validation_state, source_provenance, created_at, updated_at
       ) VALUES (?, 'MLB', 'draftkings', 'draftkings_unofficial', ?, 'Main', ?, '2026-08-31T23:05:00Z', 'slate_normalized_v1', 'VALID', 'DRAFTKINGS_UNOFFICIAL_LIVE', 'x', 'x')`,
    )
    .run(row.internal_slate_id, row.provider_slate_id, row.slate_date);
  return row;
}

function insertPlayer(overrides: Partial<{ internal_slate_id: string; provider_player_id: string; internal_player_id: string | null }> = {}) {
  const row = { internal_slate_id: "s1", provider_player_id: "1", internal_player_id: null as string | null, ...overrides };
  getDb()
    .prepare(
      `INSERT INTO slate_players (internal_slate_id, provider_player_id, internal_player_id, name, team, opponent, salary, position_eligibility_json, identity_status, created_at, updated_at)
       VALUES (?, ?, ?, 'Player', 'BOS', 'TOR', 4500, '["OF"]', ?, 'x', 'x')`,
    )
    .run(row.internal_slate_id, row.provider_player_id, row.internal_player_id, row.internal_player_id ? "RESOLVED" : "UNRESOLVED");
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

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-canonical-projections-"));
  process.env.MLB_DFS_ROOT = tmpDir;
  __resetStorageForTests();
});

afterEach(() => {
  delete process.env.MLB_DFS_ROOT;
  __resetStorageForTests();
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

function writeNativeSnapshot(date: string, players: Array<{ player_id: string; native_projection: number; native_ceiling: number; native_floor: number; model_version?: string; generated_at?: string }>) {
  const doc = {
    slate_date: date,
    generated_at: "2026-08-31T18:00:00.000Z",
    model_version: "1.0.0",
    pitcher_snapshot_path: null,
    batter_snapshot_path: null,
    environment_snapshot_path: null,
    player_count: players.length,
    players: players.map((p) => ({
      player_id: p.player_id, name: "X", team: "BOS", player_type: "hitter", opponent: "TOR", game_id: "g1", salary: 4500,
      positions: ["OF"], batting_order: null,
      native_projection: p.native_projection, native_ceiling: p.native_ceiling, native_floor: p.native_floor,
      confidence: 80, variance: 2, model_version: p.model_version ?? "1.0.0",
      hitter_opportunity: null, pitcher_opportunity: null, hitter_components: null, pitcher_components: null,
      input_coverage: null, reasons: [], warnings: [],
      generated_at: p.generated_at ?? "2026-08-31T18:00:00.000Z",
      source_pitcher_snapshot_path: null, source_batter_snapshot_path: null, source_environment_snapshot_path: null,
    })),
    warnings: [],
  };
  writeJson(`native_projection_snapshots/${date}/native_projection_20260831T180000000000.json`, doc);
}

describe("MLB FINISH MODE Phase B: computeAndPersistNativeProjectionsForSlate", () => {
  it("reports SLATE_NOT_FOUND honestly for an unknown internalSlateId", async () => {
    const result = await computeAndPersistNativeProjectionsForSlate("no-such-slate");
    expect(result.status).toBe("SLATE_NOT_FOUND");
  });

  it("reports NO_SNAPSHOT honestly when the Native engine hasn't produced anything for this date yet -- never fabricates", async () => {
    insertSlate();
    insertPlayer();
    const result = await computeAndPersistNativeProjectionsForSlate("s1");
    expect(result.status).toBe("NO_SNAPSHOT");
    expect(result.playersUpdated).toBe(0);
  });

  it("persists real projections onto the SAME slate_players' key -- only for players with BOTH resolved identity AND Native coverage", async () => {
    insertSlate();
    insertResolvedPlayer("ip-1", "660271");
    insertPlayer({ provider_player_id: "1", internal_player_id: "ip-1" }); // resolved AND covered
    insertPlayer({ provider_player_id: "2", internal_player_id: null }); // unresolved -- must stay absent
    await writeNativeSnapshot("2026-08-31", [{ player_id: "660271", native_projection: 12.4, native_ceiling: 20.1, native_floor: 3.2 }]);

    const result = await computeAndPersistNativeProjectionsForSlate("s1");
    expect(result.status).toBe("OK");
    expect(result.playersUpdated).toBe(1);

    const rows = await getCanonicalProjectionsForSlate("s1");
    expect(rows.get("1")).toEqual(expect.objectContaining({ projection: 12.4, ceiling: 20.1, floor: 3.2, model_version: "1.0.0" }));
    expect(rows.has("2")).toBe(false); // unresolved identity -- honestly absent, never guessed
  });

  it("resolved identity but NO Native coverage for that specific player stays honestly absent", async () => {
    insertSlate();
    insertResolvedPlayer("ip-1", "660271");
    insertPlayer({ provider_player_id: "1", internal_player_id: "ip-1" });
    await writeNativeSnapshot("2026-08-31", [{ player_id: "999999", native_projection: 5, native_ceiling: 9, native_floor: 1 }]); // different player

    const result = await computeAndPersistNativeProjectionsForSlate("s1");
    expect(result.status).toBe("OK");
    expect(result.playersUpdated).toBe(0);
    const rows = await getCanonicalProjectionsForSlate("s1");
    expect(rows.size).toBe(0);
  });

  it("re-running after the Native engine updates (real lineup/model change) updates the SAME row -- never duplicates", async () => {
    insertSlate();
    insertResolvedPlayer("ip-1", "660271");
    insertPlayer({ provider_player_id: "1", internal_player_id: "ip-1" });
    await writeNativeSnapshot("2026-08-31", [{ player_id: "660271", native_projection: 10, native_ceiling: 15, native_floor: 2 }]);
    await computeAndPersistNativeProjectionsForSlate("s1");

    await writeNativeSnapshot("2026-08-31", [{ player_id: "660271", native_projection: 14.5, native_ceiling: 22, native_floor: 4 }]);
    await computeAndPersistNativeProjectionsForSlate("s1");

    const rows = await getCanonicalProjectionsForSlate("s1");
    expect(rows.get("1")?.projection).toBe(14.5);
    const count = (getDb().prepare("SELECT COUNT(*) as c FROM canonical_slate_player_projections WHERE internal_slate_id='s1'").get() as { c: number }).c;
    expect(count).toBe(1);
  });
});

describe("MLB FINISH MODE Phase B: refreshCanonicalProjectionsForDate", () => {
  it("recomputes every real VALID slate for the date, isolating one slate's failure from the others", async () => {
    insertSlate({ internal_slate_id: "s1", provider_slate_id: "dkunofficial-1" });
    insertResolvedPlayer("ip-1", "660271");
    insertPlayer({ internal_slate_id: "s1", provider_player_id: "1", internal_player_id: "ip-1" });

    insertSlate({ internal_slate_id: "s2", provider_slate_id: "dkunofficial-2" });
    insertPlayer({ internal_slate_id: "s2", provider_player_id: "2", internal_player_id: null });

    await writeNativeSnapshot("2026-08-31", [{ player_id: "660271", native_projection: 8, native_ceiling: 12, native_floor: 2 }]);

    const result = await refreshCanonicalProjectionsForDate("2026-08-31");
    expect(result.slatesFound).toBe(2);
    // s1 gets a real update; s2 has no resolved/covered player, so it's an
    // honest zero-players-updated OK, not a failure.
    const s1 = result.perSlate.find((s) => s.internalSlateId === "s1")!;
    const s2 = result.perSlate.find((s) => s.internalSlateId === "s2")!;
    expect(s1.status).toBe("OK");
    expect(s1.playersUpdated).toBe(1);
    expect(s2.status).toBe("OK");
    expect(s2.playersUpdated).toBe(0);
  });
});
