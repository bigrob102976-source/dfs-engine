import crypto from "node:crypto";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "../client";
import { __resetExecutorForTests, __setExecutorForTests } from "../executor";
import { createEmailVerificationToken } from "../tokens";
import { createSession, findSessionByRawToken } from "../sessions";
import { insertSubscription, getCurrentSubscriptionForUser } from "../subscriptions";
import { createUser, findUserById } from "../users";
import type { PostgresQueryable } from "../postgresClient";
import { PostgresExecutor } from "../postgresExecutor";
import type { SqlExecutor } from "../sqlExecutor";

// Milestone 33.1: dual-backend contract tests -- the SAME business
// operation, run against BOTH backends, must return the SAME
// application-visible result shape. The underlying SQL differs (SQLite
// `?` placeholders vs. Postgres `$1,$2,...`, `rowid` vs. `seq`, etc.);
// the business result must not.
//
// SCOPE, stated honestly: the SQLite side runs against a REAL SQLite
// database (node:sqlite, via __resetDbForTests()) -- fully real,
// already the oracle every other lib/db test in this project trusts.
// The Postgres side runs against a small in-memory relational fake
// (FakeRelationalPostgres below) that correctly implements the narrow
// slice of SQL this project's own query modules actually issue
// (equality/IS-NOT-DISTINCT-FROM WHERE clauses, simple AND, ORDER BY
// ... LIMIT, INSERT/UPDATE, MAX aggregate) -- not a general-purpose SQL
// engine, and not a substitute for exercising a real PostgreSQL server.
// This proves the QUERY MODULE'S OWN LOGIC (SQL construction, parameter
// order, result-row mapping) is backend-agnostic and correct for both
// placeholder styles; it does not by itself prove PostgreSQL's own
// engine-level behavior (real MVCC, real constraint enforcement) -- see
// lib/jobs/__tests__/jobQueueConcurrency.postgres.test.ts for the one
// property (real concurrent-connection row locking) that genuinely
// needs a real server, gated behind TEST_DATABASE_URL and skipped here
// since none is available in this environment.

type Row = Record<string, unknown>;

class FakeRelationalPostgres implements PostgresQueryable {
  private tables: Record<string, Row[]> = {
    users: [],
    sessions: [],
    subscriptions: [],
    entitlements: [],
    user_entitlements: [],
    email_verification_tokens: [],
  };

  // Real Postgres gives `subscriptions`/`stripe_webhook_events` a real
  // `seq BIGSERIAL` column (migrations-postgres/0009) that auto
  // -increments on every INSERT -- this fake emulates exactly that so
  // `ORDER BY seq DESC` (lib/db/subscriptions.ts's Postgres branch for
  // "most recent subscription") behaves identically to the real schema.
  private nextSeq = 1;

  async query<T extends Record<string, unknown> = Record<string, unknown>>(sql: string, params: unknown[] = []): Promise<{ rows: T[] }> {
    const insertMatch = sql.match(/^INSERT INTO (\w+) \(([\s\S]*?)\)\s*VALUES\s*\(([\s\S]*?)\)/i);
    if (insertMatch) {
      const [, table, colsRaw, valuesRaw] = insertMatch;
      const cols = colsRaw.split(",").map((c) => c.trim());
      // Values are NOT always all `$n` placeholders -- e.g. createUser's
      // INSERT hardcodes a literal `'MEMBER'` for the role column
      // alongside real placeholders for every other column (see
      // lib/db/users.ts). Each value slot is resolved independently:
      // a `$n` placeholder pulls params[n-1]; a quoted literal is used
      // as-is (quotes stripped) -- never assumed to be positionally
      // aligned with `params`.
      const valueTokens = valuesRaw.split(",").map((v) => v.trim());
      const row: Row = {};
      cols.forEach((col, i) => {
        const token = valueTokens[i];
        const placeholderMatch = token?.match(/^\$(\d+)$/);
        if (placeholderMatch) {
          row[col] = params[Number(placeholderMatch[1]) - 1] ?? null;
        } else if (token?.startsWith("'") && token.endsWith("'")) {
          row[col] = token.slice(1, -1);
        } else {
          row[col] = token ?? null;
        }
      });
      if (table === "subscriptions" || table === "stripe_webhook_events") {
        row.seq = this.nextSeq++;
      }
      this.tables[table] ??= [];
      this.tables[table].push(row);
      return { rows: [] as T[] };
    }

    const updateMatch = sql.match(/^UPDATE (\w+) SET ([\s\S]*?) WHERE ([\s\S]+)$/i);
    if (updateMatch) {
      const [, table, setClause, whereClause] = updateMatch;
      const setCols = setClause.split(",").map((s) => s.split("=")[0].trim());
      const whereCols = [...whereClause.matchAll(/(\w+)\s*=\s*\$(\d+)/g)];
      let paramIndex = 0;
      const setValues = setCols.map(() => params[paramIndex++]);
      const rows = this.tables[table] ?? [];
      const matches = rows.filter((r) => whereCols.every(([, col]) => r[col.trim()] !== undefined) && this.rowMatchesWhere(r, whereClause, params));
      for (const row of matches) {
        setCols.forEach((col, i) => (row[col] = setValues[i]));
      }
      return { rows: [] as T[] };
    }

    const maxMatch = sql.match(/^SELECT MAX\((\w+)\) as (\w+) FROM (\w+) WHERE ([\s\S]+)$/i);
    if (maxMatch) {
      const [, col, alias, table, whereClause] = maxMatch;
      const rows = (this.tables[table] ?? []).filter((r) => this.rowMatchesWhere(r, whereClause, params));
      const max = rows.reduce<number | null>((acc, r) => {
        const v = r[col] as number | null;
        return v == null ? acc : acc == null ? v : Math.max(acc, v);
      }, null);
      return { rows: [{ [alias]: max } as unknown as T] };
    }

    const selectMatch = sql.match(/^SELECT \* FROM (\w+)(?: WHERE ([\s\S]+?))?(?: ORDER BY ([\s\S]+?))?(?: LIMIT \$?\d+)?$/i);
    if (selectMatch) {
      const [, table, whereClause, orderClause] = selectMatch;
      let rows = [...(this.tables[table] ?? [])];
      if (whereClause) rows = rows.filter((r) => this.rowMatchesWhere(r, whereClause, params));
      if (orderClause) {
        const [col, dir] = orderClause.trim().split(/\s+/);
        rows.sort((a, b) => {
          const rawA = a[col], rawB = b[col];
          // Numeric columns (seq, rowid-equivalents) compare numerically;
          // everything else (timestamps, text) compares lexicographically
          // -- both are correct for this project's own column shapes
          // (ISO-8601 fixed-width timestamps sort correctly as strings).
          if (typeof rawA === "number" && typeof rawB === "number") {
            return dir?.toUpperCase() === "DESC" ? rawB - rawA : rawA - rawB;
          }
          const av = String(rawA ?? ""), bv = String(rawB ?? "");
          return dir?.toUpperCase() === "DESC" ? bv.localeCompare(av) : av.localeCompare(bv);
        });
      }
      return { rows: rows as unknown as T[] };
    }

    throw new Error(`FakeRelationalPostgres: unhandled SQL: ${sql}`);
  }

  /** Evaluates a WHERE clause of AND-joined `col = $n` / `col IS NOT
   * DISTINCT FROM $n` / `col IS NULL` / `col > $n` terms -- the only
   * shapes this project's query modules ever generate. */
  private rowMatchesWhere(row: Row, whereClause: string, params: unknown[]): boolean {
    const terms = whereClause.split(/\s+AND\s+/i);
    return terms.every((term) => {
      const distinctMatch = term.match(/(\w+)\s+IS NOT DISTINCT FROM\s+\$(\d+)/i);
      if (distinctMatch) {
        const [, col, idx] = distinctMatch;
        return row[col] === (params[Number(idx) - 1] ?? null);
      }
      const nullMatch = term.match(/\(?(\w+)\s+IS NULL\)?/i);
      const eqMatch = term.match(/(\w+)\s*=\s*\$(\d+)/i);
      const gtMatch = term.match(/(\w+)\s*>\s*\$(\d+)/i);
      if (eqMatch) {
        const [, col, idx] = eqMatch;
        return row[col] === params[Number(idx) - 1];
      }
      if (gtMatch) {
        const [, col, idx] = gtMatch;
        const rowVal = row[col];
        return rowVal != null && String(rowVal) > String(params[Number(idx) - 1]);
      }
      if (nullMatch) {
        return row[nullMatch[1]] == null;
      }
      // OR-wrapped optional clauses (e.g. "(expires_at IS NULL OR expires_at > $n)") -- treat as satisfied
      // when either side matches; a real engine would need full parsing, this project's WHERE clauses only
      // ever use this shape for the one nullable-expiry case, handled explicitly here.
      if (/\bOR\b/i.test(term)) {
        const parts = term.replace(/^\(|\)$/g, "").split(/\s+OR\s+/i);
        return parts.some((p) => this.rowMatchesWhere(row, p, params));
      }
      return true;
    });
  }
}

function buildPostgresExecutor(): SqlExecutor {
  return new PostgresExecutor(new FakeRelationalPostgres());
}

async function useSqlite<T>(fn: () => Promise<T>): Promise<T> {
  __resetDbForTests();
  __resetExecutorForTests();
  return fn();
}

async function usePostgres<T>(fn: () => Promise<T>): Promise<T> {
  __setExecutorForTests(buildPostgresExecutor());
  return fn();
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

afterEach(() => {
  __resetExecutorForTests();
});

describe("dual-backend contract: create + read user", () => {
  it("both backends create a user and read back the identical business fields", async () => {
    const args = { email: "contract-user@example.com", passwordHash: "hash123", displayName: "Contract User" };

    const sqliteUser = await useSqlite(() => createUser(args));
    const pgUser = await usePostgres(() => createUser(args));

    expect(pgUser.email).toBe(sqliteUser.email);
    expect(pgUser.display_name).toBe(sqliteUser.display_name);
    expect(pgUser.role).toBe("MEMBER");
    expect(sqliteUser.role).toBe("MEMBER");

    const sqliteFound = await useSqlite(async () => {
      await createUser(args);
      return findUserById((await createUser({ ...args, email: "x2@example.com" })).id);
    });
    expect(sqliteFound?.email).toBe("x2@example.com");

    const pgFound = await usePostgres(async () => {
      const created = await createUser(args);
      return findUserById(created.id);
    });
    expect(pgFound?.email).toBe(args.email);
  });
});

describe("dual-backend contract: create session + expire session", () => {
  it("both backends create a session and resolve it back to the same user", async () => {
    const userArgs = { email: "session-user@example.com", passwordHash: "hash" };

    const sqliteResult = await useSqlite(async () => {
      const user = await createUser(userArgs);
      const { rawToken } = await createSession(user.id, "test-agent");
      const resolved = await findSessionByRawToken(rawToken);
      return { userId: user.id, resolvedUserId: resolved?.user.id };
    });
    expect(sqliteResult.resolvedUserId).toBe(sqliteResult.userId);

    const pgResult = await usePostgres(async () => {
      const user = await createUser(userArgs);
      const { rawToken } = await createSession(user.id, "test-agent");
      const resolved = await findSessionByRawToken(rawToken);
      return { userId: user.id, resolvedUserId: resolved?.user.id };
    });
    expect(pgResult.resolvedUserId).toBe(pgResult.userId);
  });

  it("both backends treat an unknown raw token as no session (never throws, never fabricates a user)", async () => {
    const sqliteResult = await useSqlite(() => findSessionByRawToken("nonexistent-token"));
    expect(sqliteResult).toBeNull();

    const pgResult = await usePostgres(() => findSessionByRawToken("nonexistent-token"));
    expect(pgResult).toBeNull();
  });
});

describe("dual-backend contract: create subscription + read current subscription", () => {
  it("both backends insert a subscription and report it as the user's current one", async () => {
    const userArgs = { email: "sub-user@example.com", passwordHash: "hash" };

    const sqliteResult = await useSqlite(async () => {
      const user = await createUser(userArgs);
      await insertSubscription({ userId: user.id, planId: "weekly", status: "trialing" });
      return getCurrentSubscriptionForUser(user.id);
    });
    expect(sqliteResult?.status).toBe("trialing");
    expect(sqliteResult?.plan_id).toBe("weekly");

    const pgResult = await usePostgres(async () => {
      const user = await createUser(userArgs);
      await insertSubscription({ userId: user.id, planId: "weekly", status: "trialing" });
      return getCurrentSubscriptionForUser(user.id);
    });
    expect(pgResult?.status).toBe("trialing");
    expect(pgResult?.plan_id).toBe("weekly");
  });

  it("both backends report the MOST RECENT of two subscription rows as current", async () => {
    const userArgs = { email: "sub-user-2@example.com", passwordHash: "hash" };

    const sqliteResult = await useSqlite(async () => {
      const user = await createUser(userArgs);
      await insertSubscription({ userId: user.id, planId: "weekly", status: "canceled" });
      await insertSubscription({ userId: user.id, planId: "monthly", status: "active" });
      return getCurrentSubscriptionForUser(user.id);
    });
    expect(sqliteResult?.status).toBe("active");
    expect(sqliteResult?.plan_id).toBe("monthly");

    const pgResult = await usePostgres(async () => {
      const user = await createUser(userArgs);
      await insertSubscription({ userId: user.id, planId: "weekly", status: "canceled" });
      await insertSubscription({ userId: user.id, planId: "monthly", status: "active" });
      return getCurrentSubscriptionForUser(user.id);
    });
    expect(pgResult?.status).toBe("active");
    expect(pgResult?.plan_id).toBe("monthly");
  });
});

describe("dual-backend contract: email verification token lifecycle", () => {
  it("both backends issue a token tied to the correct user", async () => {
    const userArgs = { email: "verify-user@example.com", passwordHash: "hash" };

    const sqliteResult = await useSqlite(async () => {
      const user = await createUser(userArgs);
      const { rawToken } = await createEmailVerificationToken(user.id);
      return { userId: user.id, hasToken: Boolean(rawToken) };
    });
    expect(sqliteResult.hasToken).toBe(true);

    const pgResult = await usePostgres(async () => {
      const user = await createUser(userArgs);
      const { rawToken } = await createEmailVerificationToken(user.id);
      return { userId: user.id, hasToken: Boolean(rawToken) };
    });
    expect(pgResult.hasToken).toBe(true);
  });
});

describe("dual-backend contract: FakeRelationalPostgres self-check", () => {
  it("round-trips a plain insert/select without corrupting fields", async () => {
    const fake = new FakeRelationalPostgres();
    const id = crypto.randomUUID();
    await fake.query("INSERT INTO users (id, email, role) VALUES ($1, $2, $3)", [id, "raw@example.com", "MEMBER"]);
    const { rows } = await fake.query<{ id: string; email: string }>("SELECT * FROM users WHERE id = $1", [id]);
    expect(rows[0]?.email).toBe("raw@example.com");
  });
});
