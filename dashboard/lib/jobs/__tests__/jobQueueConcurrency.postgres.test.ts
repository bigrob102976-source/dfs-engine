import { Pool } from "pg";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { __resetExecutorForTests, __setExecutorForTests } from "../../db/executor";
import { runPostgresMigrations } from "../../db/postgresClient";
import { PostgresExecutor } from "../../db/postgresExecutor";
import { claimNextQueuedJob } from "../queue";

// Milestone 33.1: the REAL-server counterpart to
// jobQueueConcurrency.test.ts's in-memory-fake proof. Only this file can
// actually prove genuine two-CONNECTION MVCC race safety (two real
// Postgres backends racing for the same row) -- the in-memory fake
// cannot, by construction, create real concurrent connections.
//
// SAFETY: requires TEST_DATABASE_URL specifically -- deliberately NOT
// DATABASE_URL (the variable every production code path reads), so this
// suite can never accidentally point at a real production database by
// inheriting an operator's existing environment. Skipped entirely
// (never a failure) when TEST_DATABASE_URL is unset -- e.g. in this
// development environment, which has no local Postgres server or Docker
// available (confirmed during the M33.0 audit). Runs automatically the
// moment a real disposable test database is configured (CI, or a
// developer's own local Postgres).
const TEST_DATABASE_URL = process.env.TEST_DATABASE_URL;

describe.skipIf(!TEST_DATABASE_URL)("claimNextQueuedJob -- real PostgreSQL concurrency", () => {
  const pool = TEST_DATABASE_URL ? new Pool({ connectionString: TEST_DATABASE_URL }) : null;

  beforeAll(async () => {
    if (!pool) return;
    await runPostgresMigrations(pool);
    await pool.query("DELETE FROM jobs");
  });

  afterAll(async () => {
    if (!pool) return;
    await pool.query("DELETE FROM jobs");
    await pool.end();
  });

  it("only one of two REAL concurrent connections claims the same QUEUED job", async () => {
    await pool!.query(
      `INSERT INTO jobs (id, job_type, slate_date, slate_id, status, created_at, updated_at, progress, attempt_count, max_attempts)
       VALUES ('pg-concurrency-job-1', 'PROCESS_SLATE', '2026-08-19', 'main', 'QUEUED', now()::text, now()::text, 0, 0, 3)`,
    );

    __setExecutorForTests(new PostgresExecutor(pool!, pool!));
    try {
      // Two genuinely independent claim attempts, fired together --
      // each goes through the real Pool, which may hand them different
      // underlying connections, exercising real row-level locking.
      const results = await Promise.all([claimNextQueuedJob("worker-a"), claimNextQueuedJob("worker-b")]);
      const claimed = results.filter((r) => r !== null);
      expect(claimed).toHaveLength(1);
      expect(claimed[0]!.id).toBe("pg-concurrency-job-1");

      const { rows } = await pool!.query("SELECT status, worker_id FROM jobs WHERE id = 'pg-concurrency-job-1'");
      expect(rows[0].status).toBe("RUNNING");
      expect(["worker-a", "worker-b"]).toContain(rows[0].worker_id);
    } finally {
      __resetExecutorForTests();
    }
  });
});
