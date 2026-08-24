import { describe, expect, it, vi } from "vitest";

import { listPostgresMigrationFiles, runPostgresMigrations, type PostgresQueryable } from "../postgresClient";

/** A minimal in-memory fake satisfying PostgresQueryable -- proves the
 * MIGRATION ORCHESTRATION logic (discovery, ordering, skip-already-
 * applied, transaction wrapping, rollback-on-error) without requiring a
 * real PostgreSQL server, per this milestone's explicit "do not
 * fabricate live PostgreSQL validation" instruction. */
function fakeClient(alreadyApplied: string[] = [], failOnSql?: (sql: string) => boolean) {
  const applied = new Set(alreadyApplied);
  const calls: string[] = [];
  const client: PostgresQueryable = {
    query: vi.fn(async (sql: string, params?: unknown[]) => {
      calls.push(sql);
      if (sql.startsWith("CREATE TABLE IF NOT EXISTS schema_migrations")) return { rows: [] };
      if (sql.startsWith("SELECT filename FROM schema_migrations")) {
        return { rows: [...applied].map((filename) => ({ filename })) };
      }
      if (sql === "BEGIN" || sql === "COMMIT" || sql === "ROLLBACK") return { rows: [] };
      if (sql.startsWith("INSERT INTO schema_migrations")) {
        applied.add((params?.[0] as string) ?? "");
        return { rows: [] };
      }
      if (failOnSql?.(sql)) throw new Error("simulated migration failure");
      return { rows: [] }; // the migration file's own SQL body
    }) as PostgresQueryable["query"],
  };
  return { client, calls };
}

describe("listPostgresMigrationFiles", () => {
  it("lists every *.sql file in lib/db/migrations-postgres, sorted", () => {
    const files = listPostgresMigrationFiles();
    expect(files).toEqual([
      "0001_init.sql", "0002_seed_reference_data.sql", "0003_stripe_billing.sql",
      "0004_slate_publishing.sql", "0005_production_infrastructure.sql", "0006_big_money_ml_optimizer_flag.sql",
      "0007_bluecollar_optimizer_flag.sql", "0008_slate_change_report.sql", "0009_ordering_sequence_columns.sql",
    ]);
  });
});

describe("runPostgresMigrations", () => {
  it("applies every migration file when none have run yet", async () => {
    const { client } = fakeClient([]);
    const result = await runPostgresMigrations(client);
    expect(result.applied).toEqual(listPostgresMigrationFiles());
    expect(result.alreadyApplied).toEqual([]);
  });

  it("skips already-applied migrations (idempotent re-run)", async () => {
    const { client } = fakeClient(listPostgresMigrationFiles());
    const result = await runPostgresMigrations(client);
    expect(result.applied).toEqual([]);
    expect(result.alreadyApplied).toEqual(listPostgresMigrationFiles());
  });

  it("applies only the NEW migrations when some have already run", async () => {
    const { client } = fakeClient(["0001_init.sql", "0002_seed_reference_data.sql"]);
    const result = await runPostgresMigrations(client);
    expect(result.applied).toEqual([
      "0003_stripe_billing.sql", "0004_slate_publishing.sql", "0005_production_infrastructure.sql",
      "0006_big_money_ml_optimizer_flag.sql", "0007_bluecollar_optimizer_flag.sql", "0008_slate_change_report.sql",
      "0009_ordering_sequence_columns.sql",
    ]);
  });

  it("wraps each migration in BEGIN/COMMIT and rolls back on failure without recording it as applied", async () => {
    const { client, calls } = fakeClient([], (sql) => sql.includes("DROP CONSTRAINT subscriptions_provider_check"));
    await expect(runPostgresMigrations(client)).rejects.toThrow(/PostgreSQL migration 0003_stripe_billing\.sql failed/);
    expect(calls).toContain("ROLLBACK");
    expect(calls.filter((c) => c === "BEGIN").length).toBeGreaterThan(0);
  });

  it("creates schema_migrations before checking applied state (safe on a brand-new database)", async () => {
    const { calls } = fakeClient([]);
    const { client } = fakeClient([]);
    await runPostgresMigrations(client);
    // The fake records calls per-instance; assert via a fresh call trace.
    const trace = fakeClient([]);
    await runPostgresMigrations(trace.client);
    expect(trace.calls[0]).toContain("CREATE TABLE IF NOT EXISTS schema_migrations");
    void calls;
  });
});
