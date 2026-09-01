import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests, getDb } from "../client";

// M1: real-SQLite verification of the additive foundation migration
// (0009_slate_identity_foundation.sql). Mirrors migrate.test.ts's
// existing pattern of exercising real constraint/FK behavior via
// getDb() rather than fabricating a live PostgreSQL server (see
// postgresClient.test.ts's identical "do not fabricate live PostgreSQL
// validation" precedent) -- the SQL bodies are shared verbatim across
// both dialects (see the migration's own header comment), so this is a
// real, meaningful check of the schema this milestone ships.

beforeEach(() => {
  __resetDbForTests();
});

function insertPlayer(db: ReturnType<typeof getDb>, id: string, name = "Flex Player") {
  db.prepare(
    "INSERT INTO players (internal_player_id, sport, canonical_name, normalized_name, active, created_at, updated_at) VALUES (?, 'MLB', ?, ?, 1, 'x', 'x')",
  ).run(id, name, name.toLowerCase());
}

function insertExternalId(
  db: ReturnType<typeof getDb>,
  overrides: Partial<{
    id: string; internalPlayerId: string; provider: string; externalId: string; isCurrent: number; validTo: string | null;
  }> = {},
) {
  const row = {
    id: "ext-1", internalPlayerId: "p1", provider: "draftkings", externalId: "999", isCurrent: 1, validTo: null,
    ...overrides,
  };
  db.prepare(
    `INSERT INTO player_external_ids
      (id, internal_player_id, sport, provider, external_id, external_id_type, match_method, match_confidence, is_current, valid_from, valid_to, created_at, updated_at)
     VALUES (?, ?, 'MLB', ?, ?, 'player_id', 'existing_crosswalk', 1.0, ?, 'x', ?, 'x', 'x')`,
  ).run(row.id, row.internalPlayerId, row.provider, row.externalId, row.isCurrent, row.validTo);
}

describe("M1 slate identity foundation migration", () => {
  it("applies cleanly and creates all five tables", () => {
    const db = getDb();
    const tables = (db.prepare("SELECT name FROM sqlite_master WHERE type='table'").all() as Array<{ name: string }>).map((r) => r.name);
    for (const expected of ["players", "player_external_ids", "slates", "slate_players", "identity_review_queue"]) {
      expect(tables).toContain(expected);
    }
  });

  it("records the migration in schema_migrations", () => {
    const db = getDb();
    const row = db.prepare("SELECT filename FROM schema_migrations WHERE filename = ?").get("0009_slate_identity_foundation.sql");
    expect(row).toBeTruthy();
  });

  it("every documented index exists", () => {
    const db = getDb();
    const indexes = (db.prepare("SELECT name FROM sqlite_master WHERE type='index'").all() as Array<{ name: string }>).map((r) => r.name);
    for (const expected of [
      "idx_players_sport", "idx_players_sport_normalized_name",
      "idx_player_external_ids_internal_player", "idx_player_external_ids_provider_external", "idx_player_external_ids_sport",
      "idx_player_external_ids_current_external", "idx_player_external_ids_current_per_player",
      "idx_slates_provider_identity", "idx_slates_sport_date", "idx_slates_provider_slate_id", "idx_slates_validation_state",
      "idx_slate_players_internal_player", "idx_slate_players_internal_slate", "idx_slate_players_identity_status", "idx_slate_players_team",
      "idx_identity_review_queue_status", "idx_identity_review_queue_sport_provider",
    ]) {
      expect(indexes).toContain(expected);
    }
  });

  it("enforces the player_external_ids -> players foreign key", () => {
    const db = getDb();
    expect(() =>
      db.prepare(
        "INSERT INTO player_external_ids (id, internal_player_id, sport, provider, external_id, external_id_type, match_method, match_confidence, valid_from, created_at, updated_at) VALUES ('e1','no-such-player','MLB','draftkings','999','player_id','existing_crosswalk',1.0,'x','x','x')",
      ).run(),
    ).toThrow();
  });

  it("enforces the slate_players -> slates foreign key", () => {
    const db = getDb();
    expect(() =>
      db.prepare(
        "INSERT INTO slate_players (internal_slate_id, provider_player_id, name, team, salary, identity_status, created_at, updated_at) VALUES ('no-such-slate','999','Player','BOS',4000,'UNRESOLVED','x','x')",
      ).run(),
    ).toThrow();
  });

  it("allows slate_players.internal_player_id to be null (unresolved identity is servable)", () => {
    const db = getDb();
    db.prepare(
      "INSERT INTO slates (internal_slate_id, sport, site, provider, provider_slate_id, slate_date, first_game_start_utc, schema_version, created_at, updated_at) VALUES ('slate-1','MLB','draftkings','draftkings_unofficial','152904','2026-08-31','2026-08-31T23:05:00Z','slate_normalized_v1','x','x')",
    ).run();
    expect(() =>
      db.prepare(
        "INSERT INTO slate_players (internal_slate_id, provider_player_id, internal_player_id, name, team, salary, identity_status, created_at, updated_at) VALUES ('slate-1','999',NULL,'Player','BOS',4000,'UNRESOLVED','x','x')",
      ).run(),
    ).not.toThrow();
  });

  it("rejects a second CURRENT mapping for the same (provider, external_id, sport)", () => {
    const db = getDb();
    insertPlayer(db, "p1");
    insertPlayer(db, "p2", "Other Player");
    insertExternalId(db, { id: "e1", internalPlayerId: "p1", externalId: "999", isCurrent: 1 });
    expect(() => insertExternalId(db, { id: "e2", internalPlayerId: "p2", externalId: "999", isCurrent: 1 })).toThrow();
  });

  it("allows historical (is_current=0) external IDs to coexist with a current one", () => {
    const db = getDb();
    insertPlayer(db, "p1");
    expect(() => {
      insertExternalId(db, { id: "e-old", internalPlayerId: "p1", externalId: "111", isCurrent: 0, validTo: "2025-01-01" });
      insertExternalId(db, { id: "e-new", internalPlayerId: "p1", externalId: "999", isCurrent: 1 });
    }).not.toThrow();
    const rows = db.prepare("SELECT external_id, is_current FROM player_external_ids WHERE internal_player_id = 'p1' ORDER BY external_id").all();
    expect(rows).toEqual([
      { external_id: "111", is_current: 0 },
      { external_id: "999", is_current: 1 },
    ]);
  });

  it("rejects a second CURRENT mapping for the same internal player + provider (duplicate active mapping)", () => {
    const db = getDb();
    insertPlayer(db, "p1");
    insertExternalId(db, { id: "e1", internalPlayerId: "p1", provider: "draftkings", externalId: "999", isCurrent: 1 });
    expect(() =>
      insertExternalId(db, { id: "e2", internalPlayerId: "p1", provider: "draftkings", externalId: "888", isCurrent: 1 }),
    ).toThrow();
  });

  it("enforces slates provider-identity uniqueness (sport, site, provider, provider_slate_id)", () => {
    const db = getDb();
    const insertSlate = (internalId: string) =>
      db
        .prepare(
          "INSERT INTO slates (internal_slate_id, sport, site, provider, provider_slate_id, slate_date, first_game_start_utc, schema_version, created_at, updated_at) VALUES (?, 'MLB','draftkings','draftkings_unofficial','152904','2026-08-31','2026-08-31T23:05:00Z','slate_normalized_v1','x','x')",
        )
        .run(internalId);
    insertSlate("slate-a");
    expect(() => insertSlate("slate-b")).toThrow();
  });

  it("enforces the validation_state and identity_status CHECK constraints", () => {
    const db = getDb();
    expect(() =>
      db
        .prepare(
          "INSERT INTO slates (internal_slate_id, sport, site, provider, provider_slate_id, slate_date, first_game_start_utc, schema_version, validation_state, created_at, updated_at) VALUES ('slate-x','MLB','draftkings','draftkings_unofficial','1','2026-08-31','2026-08-31T23:05:00Z','slate_normalized_v1','NOT_A_STATE','x','x')",
        )
        .run(),
    ).toThrow();
  });

  it("creates an identity_review_queue row without requiring a resolved candidate", () => {
    const db = getDb();
    expect(() =>
      db
        .prepare(
          "INSERT INTO identity_review_queue (id, sport, provider, external_id, provider_player_name, reason, status, created_at, updated_at) VALUES ('q1','MLB','draftkings','dk-ambiguous','Flex Player','Two plausible candidates.','PENDING','x','x')",
        )
        .run(),
    ).not.toThrow();
  });
});
