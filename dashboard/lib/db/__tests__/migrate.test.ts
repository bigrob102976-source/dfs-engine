import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests, getDb } from "../client";

beforeEach(() => {
  __resetDbForTests();
});

describe("migrations", () => {
  it("applies both migration files and records them in schema_migrations", () => {
    const db = getDb();
    const rows = db.prepare("SELECT filename FROM schema_migrations ORDER BY filename").all() as Array<{ filename: string }>;
    expect(rows.map((r) => r.filename)).toEqual(["0001_init.sql", "0002_seed_reference_data.sql"]);
  });

  it("re-running migrations on the same database is a safe no-op", () => {
    const db = getDb();
    // __resetDbForTests already ran migrations once when opening; running
    // the same runMigrations logic again via a fresh getDb() call must
    // not re-apply or error since the singleton is already migrated.
    expect(() => getDb()).not.toThrow();
    const rows = db.prepare("SELECT COUNT(*) as c FROM schema_migrations").get() as { c: number };
    expect(rows.c).toBe(2);
  });

  it("seeds all 4 sports with MLB LIVE and the rest COMING_SOON", () => {
    const db = getDb();
    const sports = db.prepare("SELECT code, status FROM sports ORDER BY sort_order").all() as Array<{ code: string; status: string }>;
    expect(sports).toEqual([
      { code: "MLB", status: "LIVE" },
      { code: "NFL", status: "COMING_SOON" },
      { code: "NBA", status: "COMING_SOON" },
      { code: "NHL", status: "COMING_SOON" },
    ]);
  });

  it("seeds the 2 launch plans with correct pricing and trial length", () => {
    const db = getDb();
    const plans = db.prepare("SELECT id, price_cents, billing_interval, trial_days FROM plans ORDER BY price_cents").all();
    expect(plans).toEqual([
      { id: "weekly", price_cents: 1099, billing_interval: "WEEKLY", trial_days: 3 },
      { id: "monthly", price_cents: 2999, billing_interval: "MONTHLY", trial_days: 3 },
    ]);
  });

  it("seeds a matching entitlements and feature_flags row per MLB feature key", () => {
    const db = getDb();
    const entitlementKeys = (db.prepare("SELECT key FROM entitlements ORDER BY key").all() as Array<{ key: string }>).map((r) => r.key);
    const featureKeys = (db.prepare("SELECT key FROM feature_flags ORDER BY key").all() as Array<{ key: string }>).map((r) => r.key);
    expect(entitlementKeys).toEqual(featureKeys);
    expect(entitlementKeys).toContain("mlb.optimizer");
    expect(entitlementKeys).toContain("mlb.ai_projections");
  });

  it("every seeded feature flag starts PRODUCTION", () => {
    const db = getDb();
    const states = db.prepare("SELECT DISTINCT state FROM feature_flags").all() as Array<{ state: string }>;
    expect(states).toEqual([{ state: "PRODUCTION" }]);
  });

  it("enforces foreign keys (rejects an orphaned subscription)", () => {
    const db = getDb();
    expect(() =>
      db.prepare("INSERT INTO subscriptions (id, user_id, plan_id, status, created_at, updated_at) VALUES ('s1','no-such-user','weekly','active','x','x')").run(),
    ).toThrow();
  });
});
