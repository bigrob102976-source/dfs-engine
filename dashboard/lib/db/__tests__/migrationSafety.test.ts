import { describe, expect, it } from "vitest";

import { findBlockedMigrations, MIGRATION_SAFETY_OVERRIDE_MARKER, scanMigrationSql } from "../migrationSafety";

describe("scanMigrationSql -- additive statements allowed", () => {
  it("allows CREATE TABLE", () => {
    const result = scanMigrationSql("CREATE TABLE foo (id TEXT PRIMARY KEY);");
    expect(result.dangerous).toBe(false);
    expect(result.blocked).toBe(false);
  });

  it("allows CREATE INDEX / CREATE UNIQUE INDEX", () => {
    const result = scanMigrationSql("CREATE INDEX idx_foo ON foo(id);\nCREATE UNIQUE INDEX idx_foo2 ON foo(id) WHERE id IS NOT NULL;");
    expect(result.dangerous).toBe(false);
  });

  it("allows ADD COLUMN", () => {
    const result = scanMigrationSql("ALTER TABLE foo ADD COLUMN bar TEXT;");
    expect(result.dangerous).toBe(false);
  });

  it("allows a real multi-statement additive migration", () => {
    const sql = `
      CREATE TABLE players (internal_player_id TEXT PRIMARY KEY, sport TEXT NOT NULL);
      CREATE INDEX idx_players_sport ON players(sport);
      ALTER TABLE slates ADD COLUMN promoted_at TEXT;
    `;
    expect(scanMigrationSql(sql).dangerous).toBe(false);
  });
});

describe("scanMigrationSql -- dangerous statements flagged and blocked", () => {
  it("flags and blocks DROP TABLE", () => {
    const result = scanMigrationSql("DROP TABLE foo;");
    expect(result.dangerous).toBe(true);
    expect(result.blocked).toBe(true);
    expect(result.findings.some((f) => f.pattern === "DROP TABLE")).toBe(true);
  });

  it("flags and blocks DROP COLUMN", () => {
    const result = scanMigrationSql("ALTER TABLE foo DROP COLUMN bar;");
    expect(result.blocked).toBe(true);
  });

  it("flags and blocks TRUNCATE", () => {
    const result = scanMigrationSql("TRUNCATE foo;");
    expect(result.blocked).toBe(true);
  });

  it("flags and blocks uncontrolled DELETE FROM", () => {
    const result = scanMigrationSql("DELETE FROM foo WHERE id = 'x';");
    expect(result.blocked).toBe(true);
  });

  it("flags and blocks a destructive ALTER COLUMN ... TYPE", () => {
    const result = scanMigrationSql("ALTER TABLE foo ALTER COLUMN bar TYPE INTEGER;");
    expect(result.blocked).toBe(true);
  });

  it("flags and blocks DROP CONSTRAINT even when immediately paired with ADD CONSTRAINT", () => {
    // Conservative by design -- see this module's own docstring on the
    // 0003_stripe_billing.sql precedent.
    const sql = "ALTER TABLE subscriptions DROP CONSTRAINT subscriptions_provider_check;\nALTER TABLE subscriptions ADD CONSTRAINT subscriptions_provider_check CHECK (provider IN ('dev','stripe'));";
    const result = scanMigrationSql(sql);
    expect(result.blocked).toBe(true);
  });
});

describe("scanMigrationSql -- comments never trigger a false positive", () => {
  it("does not flag a dangerous keyword that only appears in a SQL comment", () => {
    const sql = "-- this migration intentionally does NOT drop table anything\nCREATE TABLE foo (id TEXT PRIMARY KEY);";
    expect(scanMigrationSql(sql).dangerous).toBe(false);
  });
});

describe("scanMigrationSql -- explicit override marker", () => {
  it("requires an EXPLICIT marker string -- a vague comment does not suffice", () => {
    const sql = "-- this is fine, trust me\nDROP TABLE foo;";
    expect(scanMigrationSql(sql).blocked).toBe(true);
  });

  it("unblocks a dangerous migration when the exact override marker is present, but still reports findings", () => {
    const sql = `-- ${MIGRATION_SAFETY_OVERRIDE_MARKER}: legacy table removal, approved by <name> on <date>\nDROP TABLE foo;`;
    const result = scanMigrationSql(sql);
    expect(result.dangerous).toBe(true);
    expect(result.overridden).toBe(true);
    expect(result.blocked).toBe(false);
  });
});

describe("findBlockedMigrations", () => {
  it("returns only the files that are actually blocked", () => {
    const files = [
      { filename: "0001_ok.sql", sql: "CREATE TABLE foo (id TEXT);" },
      { filename: "0002_bad.sql", sql: "DROP TABLE foo;" },
      { filename: "0003_overridden.sql", sql: `-- ${MIGRATION_SAFETY_OVERRIDE_MARKER}\nTRUNCATE foo;` },
    ];
    const blocked = findBlockedMigrations(files);
    expect(blocked.map((b) => b.filename)).toEqual(["0002_bad.sql"]);
  });

  it("returns an empty list when nothing is blocked", () => {
    expect(findBlockedMigrations([{ filename: "0001.sql", sql: "CREATE TABLE foo (id TEXT);" }])).toEqual([]);
  });
});
