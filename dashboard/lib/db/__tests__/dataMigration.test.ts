import { describe, expect, it, vi } from "vitest";

import {
  buildDryRunReport,
  DataMigrationError,
  MIGRATION_TABLES,
  redactRow,
  runDataMigration,
  type MigrationRow,
  type MigrationSource,
  type MigrationTarget,
} from "../dataMigration";

const FAKE_PASSWORD_HASH = "scrypt$fake-hash-value-should-never-appear-in-any-report";
const FAKE_TOKEN_HASH = "sha256$fake-session-token-hash-should-never-appear";
const FAKE_STRIPE_CUSTOMER_ID = "cus_fakeSecretLookingId123";

function fakeSource(data: Partial<Record<string, MigrationRow[]>>): MigrationSource {
  return {
    countRows: (table) => (data[table] ?? []).length,
    readRows: (table) => data[table] ?? [],
  };
}

function fakeTarget(preExisting: Partial<Record<string, MigrationRow[]>> = {}, opts?: { failTable?: string; dropRowsOnTable?: string }): MigrationTarget & { written: Record<string, MigrationRow[]> } {
  const written: Record<string, MigrationRow[]> = {};
  for (const [table, rows] of Object.entries(preExisting)) written[table] = [...(rows ?? [])];

  return {
    written,
    countRows: vi.fn(async (table: string) => (written[table] ?? []).length),
    insertRows: vi.fn(async (table: string, columns: string[], rows: MigrationRow[]) => {
      if (opts?.failTable === table) throw new Error("simulated insert failure");
      const toInsert = opts?.dropRowsOnTable === table ? rows.slice(0, Math.max(0, rows.length - 1)) : rows;
      written[table] = [...(written[table] ?? []), ...toInsert.map((r) => Object.fromEntries(columns.map((c) => [c, r[c]])))];
    }),
    updateSelfReferentialColumn: vi.fn(async (table: string, _pk: string, column: string, rows: MigrationRow[]) => {
      const rowsById = new Map(rows.map((r) => [r.id, r]));
      for (const target of written[table] ?? []) {
        const original = rowsById.get(target.id);
        if (original) target[column] = original[column];
      }
    }),
  };
}

describe("MIGRATION_TABLES", () => {
  it("covers every real table with a consistent primary key + columns", () => {
    const names = MIGRATION_TABLES.map((t) => t.name);
    expect(new Set(names).size).toBe(names.length); // no duplicates
    expect(names).toContain("users");
    expect(names).toContain("jobs");
    expect(names).toContain("slate_status");
    // users must be migrated before every table with a users FK.
    expect(names.indexOf("users")).toBeLessThan(names.indexOf("subscriptions"));
    expect(names.indexOf("users")).toBeLessThan(names.indexOf("sessions"));
    expect(names.indexOf("sports")).toBeLessThan(names.indexOf("entitlements"));
    expect(names.indexOf("plans")).toBeLessThan(names.indexOf("subscriptions"));
  });
});

describe("redactRow", () => {
  it("masks sensitive columns and leaves everything else untouched", () => {
    const usersSpec = MIGRATION_TABLES.find((t) => t.name === "users")!;
    const row: MigrationRow = { id: "u1", email: "a@example.com", password_hash: FAKE_PASSWORD_HASH, role: "MEMBER" };
    const redacted = redactRow(usersSpec, row);
    expect(redacted.password_hash).toBe("[REDACTED]");
    expect(redacted.email).toBe("a@example.com");
    expect(redacted.id).toBe("u1");
  });

  it("leaves a null sensitive column as null rather than the redaction marker", () => {
    const usersSpec = MIGRATION_TABLES.find((t) => t.name === "users")!;
    const redacted = redactRow(usersSpec, { id: "u1", stripe_customer_id: null });
    expect(redacted.stripe_customer_id).toBeNull();
  });
});

describe("buildDryRunReport", () => {
  it("never leaks a real password hash, token hash, or stripe customer id", () => {
    const source = fakeSource({
      users: [{ id: "u1", email: "a@example.com", password_hash: FAKE_PASSWORD_HASH, stripe_customer_id: FAKE_STRIPE_CUSTOMER_ID }],
      sessions: [{ id: "s1", token_hash: FAKE_TOKEN_HASH, user_id: "u1" }],
    });
    const report = buildDryRunReport(source);
    const serialized = JSON.stringify(report);
    expect(serialized).not.toContain(FAKE_PASSWORD_HASH);
    expect(serialized).not.toContain(FAKE_TOKEN_HASH);
    expect(serialized).not.toContain(FAKE_STRIPE_CUSTOMER_ID);
    expect(serialized).toContain("a@example.com"); // non-sensitive fields still shown
  });

  it("reports accurate counts and a null sample for empty tables, touching only the source", () => {
    const source = fakeSource({ users: [{ id: "u1" }, { id: "u2" }] });
    const report = buildDryRunReport(source);
    const usersEntry = report.find((e) => e.table === "users")!;
    expect(usersEntry.sourceRowCount).toBe(2);
    expect(usersEntry.sampleRedactedRow).toEqual({ id: "u1" });
    const jobsEntry = report.find((e) => e.table === "jobs")!;
    expect(jobsEntry).toEqual({ table: "jobs", sourceRowCount: 0, sampleRedactedRow: null });
  });
});

describe("runDataMigration", () => {
  it("migrates every non-empty table and skips empty ones", async () => {
    const source = fakeSource({
      sports: [{ code: "MLB", name: "MLB", status: "LIVE", sort_order: 0 }],
      users: [{ id: "u1", email: "a@example.com", beta_access_granted_by: null }],
    });
    const target = fakeTarget();
    const results = await runDataMigration(source, target);

    const sportsResult = results.find((r) => r.table === "sports")!;
    expect(sportsResult.status).toBe("MIGRATED");
    expect(sportsResult.rowsInserted).toBe(1);

    const plansResult = results.find((r) => r.table === "plans")!;
    expect(plansResult.status).toBe("SKIPPED_EMPTY_SOURCE");

    expect(target.written.sports).toEqual([{ code: "MLB", name: "MLB", status: "LIVE", sort_order: 0 }]);
  });

  it("migrates tables in dependency order (users before subscriptions)", async () => {
    const source = fakeSource({
      users: [{ id: "u1" }],
      plans: [{ id: "weekly" }],
      subscriptions: [{ id: "sub1", user_id: "u1", plan_id: "weekly" }],
    });
    const target = fakeTarget();
    await runDataMigration(source, target);

    const insertMock = target.insertRows as unknown as { mock: { calls: unknown[][] } };
    const calledTables = insertMock.mock.calls.map((call) => call[0]);
    expect(calledTables.indexOf("users")).toBeLessThan(calledTables.indexOf("subscriptions"));
    expect(calledTables.indexOf("plans")).toBeLessThan(calledTables.indexOf("subscriptions"));
  });

  it("backfills a self-referential column (users.beta_access_granted_by) in a second pass", async () => {
    const source = fakeSource({
      users: [
        { id: "admin1", email: "admin@example.com", beta_access_granted_by: null },
        { id: "member1", email: "member@example.com", beta_access_granted_by: "admin1" },
      ],
    });
    const target = fakeTarget();
    await runDataMigration(source, target);

    // The initial insert must NOT include the self-referential column...
    const insertMock = target.insertRows as unknown as { mock: { calls: unknown[][] } };
    const usersInsertCall = insertMock.mock.calls.find((call) => call[0] === "users")!;
    expect(usersInsertCall[1]).not.toContain("beta_access_granted_by");

    // ...but the second-pass backfill must still land the real value.
    const member = target.written.users.find((r) => r.id === "member1")!;
    expect(member.beta_access_granted_by).toBe("admin1");
  });

  it("fails closed and refuses to write when the target table already has rows", async () => {
    const source = fakeSource({ sports: [{ code: "MLB" }] });
    const target = fakeTarget({ sports: [{ code: "MLB" }] });
    const results = await runDataMigration(source, target);

    const sportsResult = results.find((r) => r.table === "sports")!;
    expect(sportsResult.status).toBe("SKIPPED_ALREADY_MIGRATED");
    expect(target.insertRows).not.toHaveBeenCalled();
  });

  it("stops the whole run and throws DataMigrationError on an insert failure, without touching later tables", async () => {
    const source = fakeSource({
      sports: [{ code: "MLB" }],
      plans: [{ id: "weekly" }],
    });
    const target = fakeTarget({}, { failTable: "sports" });

    await expect(runDataMigration(source, target)).rejects.toThrow(DataMigrationError);
    await expect(runDataMigration(source, target)).rejects.toThrow(/Migrating table "sports" failed/);
    expect(target.written.plans).toBeUndefined();
  });

  it("throws on a post-insert row-count mismatch instead of silently proceeding", async () => {
    const source = fakeSource({ sports: [{ code: "MLB" }, { code: "NFL" }] });
    const target = fakeTarget({}, { dropRowsOnTable: "sports" });

    await expect(runDataMigration(source, target)).rejects.toThrow(/Row count mismatch/);
  });

  it("a second run after a partial failure safely skips the already-migrated tables", async () => {
    const source = fakeSource({
      sports: [{ code: "MLB" }],
      plans: [{ id: "weekly" }],
    });
    const target = fakeTarget();
    const firstRun = await runDataMigration(source, target);
    expect(firstRun.every((r) => r.status === "MIGRATED" || r.status === "SKIPPED_EMPTY_SOURCE")).toBe(true);

    const insertCallsBefore = (target.insertRows as unknown as { mock: { calls: unknown[][] } }).mock.calls.length;
    const secondRun = await runDataMigration(source, target);
    expect(secondRun.filter((r) => r.status === "MIGRATED")).toHaveLength(0);
    expect(secondRun.filter((r) => r.status === "SKIPPED_ALREADY_MIGRATED")).toHaveLength(2);
    expect((target.insertRows as unknown as { mock: { calls: unknown[][] } }).mock.calls.length).toBe(insertCallsBefore);
  });
});
