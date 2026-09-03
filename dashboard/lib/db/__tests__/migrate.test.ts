import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests, getDb } from "../client";

beforeEach(() => {
  __resetDbForTests();
});

describe("migrations", () => {
  it("applies all migration files and records them in schema_migrations", () => {
    const db = getDb();
    const rows = db.prepare("SELECT filename FROM schema_migrations ORDER BY filename").all() as Array<{ filename: string }>;
    expect(rows.map((r) => r.filename)).toEqual([
      "0001_init.sql", "0002_seed_reference_data.sql", "0003_stripe_billing.sql", "0004_slate_publishing.sql",
      "0005_production_infrastructure.sql", "0006_big_money_ml_optimizer_flag.sql", "0007_bluecollar_optimizer_flag.sql",
      "0008_slate_change_report.sql", "0009_slate_identity_foundation.sql", "0010_canonical_slate_promotion_metadata.sql",
      "0011_canonical_shadow_status.sql", "0012_canonical_serving_backend_flag.sql", "0013_canonical_slate_player_eligibility.sql",
      "0014_canonical_slate_last_validated.sql", "0015_canonical_slate_player_projections.sql",
    ]);
  });

  it("re-running migrations on the same database is a safe no-op", () => {
    const db = getDb();
    // __resetDbForTests already ran migrations once when opening; running
    // the same runMigrations logic again via a fresh getDb() call must
    // not re-apply or error since the singleton is already migrated.
    expect(() => getDb()).not.toThrow();
    const rows = db.prepare("SELECT COUNT(*) as c FROM schema_migrations").get() as { c: number };
    expect(rows.c).toBe(15);
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
    expect(entitlementKeys).toContain("mlb.big_money_ml_optimizer");
    expect(entitlementKeys).toContain("mlb.bluecollar_optimizer");
  });

  it("every 0002-seeded (page-level) feature flag starts PRODUCTION; the Big Money ML, BlueCollar, and canonical-serving capabilities start ADMIN_ONLY", () => {
    const db = getDb();
    const states = db
      .prepare("SELECT DISTINCT state FROM feature_flags WHERE key NOT IN ('mlb.big_money_ml_optimizer', 'mlb.bluecollar_optimizer', 'mlb.canonical_postgres_serving')")
      .all() as Array<{ state: string }>;
    expect(states).toEqual([{ state: "PRODUCTION" }]);

    const mlFlag = db.prepare("SELECT state FROM feature_flags WHERE key = 'mlb.big_money_ml_optimizer'").get() as { state: string };
    expect(mlFlag.state).toBe("ADMIN_ONLY");
    const bcFlag = db.prepare("SELECT state FROM feature_flags WHERE key = 'mlb.bluecollar_optimizer'").get() as { state: string };
    expect(bcFlag.state).toBe("ADMIN_ONLY");
    // M5C: seeded ADMIN_ONLY -- see migrations/0012_canonical_serving_backend_flag.sql's own docstring for why.
    const servingFlag = db.prepare("SELECT state FROM feature_flags WHERE key = 'mlb.canonical_postgres_serving'").get() as { state: string };
    expect(servingFlag.state).toBe("ADMIN_ONLY");
  });

  it("enforces foreign keys (rejects an orphaned subscription)", () => {
    const db = getDb();
    expect(() =>
      db.prepare("INSERT INTO subscriptions (id, user_id, plan_id, status, created_at, updated_at) VALUES ('s1','no-such-user','weekly','active','x','x')").run(),
    ).toThrow();
  });

  describe("0003_stripe_billing", () => {
    it("widens subscriptions.provider to allow 'stripe' (previously CHECK'd to 'dev' only)", () => {
      const db = getDb();
      db.prepare(
        "INSERT INTO users (id, email, password_hash, created_at, updated_at) VALUES ('u1','stripe-check@example.com','h','x','x')",
      ).run();
      expect(() =>
        db
          .prepare(
            "INSERT INTO subscriptions (id, user_id, plan_id, status, provider, created_at, updated_at) VALUES ('s1','u1','weekly','active','stripe','x','x')",
          )
          .run(),
      ).not.toThrow();
      expect(() =>
        db
          .prepare(
            "INSERT INTO subscriptions (id, user_id, plan_id, status, provider, created_at, updated_at) VALUES ('s2','u1','weekly','active','paypal','x','x')",
          )
          .run(),
      ).toThrow();
    });

    it("preserves existing 'dev' rows and their columns after the table rebuild", () => {
      const db = getDb();
      db.prepare(
        "INSERT INTO users (id, email, password_hash, created_at, updated_at) VALUES ('u2','dev-preserved@example.com','h','x','x')",
      ).run();
      db.prepare(
        "INSERT INTO subscriptions (id, user_id, plan_id, status, provider, trial_ends_at, created_at, updated_at) VALUES ('s3','u2','weekly','trialing','dev','2099-01-01T00:00:00Z','x','x')",
      ).run();
      const row = db.prepare("SELECT * FROM subscriptions WHERE id='s3'").get() as Record<string, unknown>;
      expect(row.provider).toBe("dev");
      expect(row.trial_ends_at).toBe("2099-01-01T00:00:00Z");
      expect(row.cancel_at_period_end).toBe(0); // new column, defaults to 0
      expect(row.provider_price_id).toBeNull();
    });

    it("rejects two subscriptions with the same non-null provider_subscription_id", () => {
      const db = getDb();
      db.prepare(
        "INSERT INTO users (id, email, password_hash, created_at, updated_at) VALUES ('u3','dupe-check@example.com','h','x','x')",
      ).run();
      db.prepare(
        "INSERT INTO subscriptions (id, user_id, plan_id, status, provider, provider_subscription_id, created_at, updated_at) VALUES ('s4','u3','weekly','active','stripe','sub_123','x','x')",
      ).run();
      expect(() =>
        db
          .prepare(
            "INSERT INTO subscriptions (id, user_id, plan_id, status, provider, provider_subscription_id, created_at, updated_at) VALUES ('s5','u3','weekly','active','stripe','sub_123','x','x')",
          )
          .run(),
      ).toThrow();
    });

    it("allows many subscriptions with a NULL provider_subscription_id (every historical dev row)", () => {
      const db = getDb();
      db.prepare(
        "INSERT INTO users (id, email, password_hash, created_at, updated_at) VALUES ('u4','null-provider-id@example.com','h','x','x')",
      ).run();
      db.prepare(
        "INSERT INTO subscriptions (id, user_id, plan_id, status, provider, created_at, updated_at) VALUES ('s6','u4','weekly','active','dev','x','x')",
      ).run();
      expect(() =>
        db
          .prepare(
            "INSERT INTO subscriptions (id, user_id, plan_id, status, provider, created_at, updated_at) VALUES ('s7','u4','weekly','canceled','dev','x','x')",
          )
          .run(),
      ).not.toThrow();
    });

    it("adds users.stripe_customer_id (unique when set) and users.trial_consumed_at", () => {
      const db = getDb();
      db.prepare(
        "INSERT INTO users (id, email, password_hash, stripe_customer_id, created_at, updated_at) VALUES ('u5','cus-check@example.com','h','cus_abc','x','x')",
      ).run();
      expect(() =>
        db
          .prepare(
            "INSERT INTO users (id, email, password_hash, stripe_customer_id, created_at, updated_at) VALUES ('u6','cus-check2@example.com','h','cus_abc','x','x')",
          )
          .run(),
      ).toThrow();
      const row = db.prepare("SELECT trial_consumed_at FROM users WHERE id='u5'").get() as { trial_consumed_at: string | null };
      expect(row.trial_consumed_at).toBeNull();
    });

    it("creates stripe_webhook_events with a unique event-id primary key", () => {
      const db = getDb();
      db.prepare("INSERT INTO stripe_webhook_events (id, type, received_at) VALUES ('evt_1','customer.subscription.updated','x')").run();
      expect(() => db.prepare("INSERT INTO stripe_webhook_events (id, type, received_at) VALUES ('evt_1','other','x')").run()).toThrow();
      const row = db.prepare("SELECT status FROM stripe_webhook_events WHERE id='evt_1'").get() as { status: string };
      expect(row.status).toBe("processing"); // default
    });
  });
});
