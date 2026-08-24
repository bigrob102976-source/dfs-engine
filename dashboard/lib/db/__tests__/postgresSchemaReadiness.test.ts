import { describe, expect, it, vi } from "vitest";

import { checkPostgresSchemaReadiness, listPostgresMigrationFiles, type PostgresQueryable } from "../postgresClient";

// Milestone 33.1: DB health-check schema-readiness -- distinct from mere
// connectivity (a fresh Postgres database connects fine but has zero
// tables until migrations are explicitly applied). Uses the same
// no-real-server-required fake-client pattern already established in
// postgresClient.test.ts.
function fakeClient(appliedFilenames: string[] | "missing_table"): PostgresQueryable {
  return {
    query: vi.fn(async (sql: string) => {
      if (sql.startsWith("SELECT filename FROM schema_migrations")) {
        if (appliedFilenames === "missing_table") throw new Error('relation "schema_migrations" does not exist');
        return { rows: appliedFilenames.map((filename) => ({ filename })) };
      }
      return { rows: [] };
    }) as PostgresQueryable["query"],
  };
}

describe("checkPostgresSchemaReadiness", () => {
  it("reports ready:true when every migration file on disk is recorded as applied", async () => {
    const result = await checkPostgresSchemaReadiness(fakeClient(listPostgresMigrationFiles()));
    expect(result.ready).toBe(true);
    expect(result.pending).toEqual([]);
    expect(result.appliedCount).toBe(result.expectedCount);
  });

  it("reports ready:false with the pending filenames when some migrations haven't been applied", async () => {
    const result = await checkPostgresSchemaReadiness(fakeClient(["0001_init.sql", "0002_seed_reference_data.sql"]));
    expect(result.ready).toBe(false);
    expect(result.pending).toContain("0009_ordering_sequence_columns.sql");
    expect(result.pending).not.toContain("0001_init.sql");
  });

  it("reports ready:false (never throws) on a brand-new database with no schema_migrations table yet", async () => {
    const result = await checkPostgresSchemaReadiness(fakeClient("missing_table"));
    expect(result.ready).toBe(false);
    expect(result.appliedCount).toBe(0);
    expect(result.pending).toEqual(listPostgresMigrationFiles());
  });

  it("never exposes SQL text or connection details -- only filenames and counts", async () => {
    const result = await checkPostgresSchemaReadiness(fakeClient([]));
    const serialized = JSON.stringify(result);
    expect(serialized).not.toMatch(/DATABASE_URL|password|postgres:\/\//i);
  });
});
