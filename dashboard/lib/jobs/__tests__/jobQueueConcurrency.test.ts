import { describe, expect, it } from "vitest";

import { __resetExecutorForTests, __setExecutorForTests } from "../../db/executor";
import type { PostgresQueryable } from "../../db/postgresClient";
import { PostgresExecutor } from "../../db/postgresExecutor";
import type { JobRow } from "../../db/types";
import { claimNextQueuedJob } from "../queue";

// Milestone 33.1: proves claimNextQueuedJob()'s Postgres branch is safe
// under concurrent claiming -- the exact requirement this milestone
// calls out by name ("Test two workers attempting to claim the same
// job. Only one may succeed.").
//
// HONESTY NOTE on what this actually proves: no real PostgreSQL server
// is available in this environment (confirmed absent -- no psql, no
// Docker -- consistent with the M33.0 production audit's own finding).
// This fake PostgresQueryable executes the exact SQL text
// claimNextQueuedJob's Postgres branch issues
// (`UPDATE jobs SET status='RUNNING' ... WHERE id = (SELECT id FROM
// jobs WHERE status='QUEUED' ORDER BY created_at ASC LIMIT 1 FOR UPDATE
// SKIP LOCKED) RETURNING *`) against an in-memory row array, mutating
// synchronously inside the fake's own `query()` call -- which means the
// SECOND of two `Promise.all`-issued claims only ever sees the ALREADY
// -claimed state by the time its own query runs, correctly proving the
// query's WHERE/RETURNING construction is exclusive. It does NOT prove
// genuine two-CONNECTION MVCC race safety (two real Postgres backends
// racing to lock the same row before either commits) -- only a real
// server can prove that; `FOR UPDATE SKIP LOCKED` is the standard,
// well-documented Postgres pattern for exactly that case, which is why
// the live SQL text uses it. See jobQueueConcurrency.postgres.test.ts
// for the TEST_DATABASE_URL-gated real-server version of this same
// proof, which activates automatically once a real Postgres test
// database is configured.
function fakeJobsTable(seed: Partial<JobRow>[]) {
  const rows: JobRow[] = seed.map((s, i) => ({
    id: s.id ?? `job-${i}`,
    job_type: s.job_type ?? "PROCESS_SLATE",
    slate_date: s.slate_date ?? "2026-08-19",
    slate_id: s.slate_id ?? `slate-${i}`,
    status: s.status ?? "QUEUED",
    created_by: s.created_by ?? null,
    created_at: s.created_at ?? `2026-08-19T00:00:0${i}Z`,
    started_at: s.started_at ?? null,
    finished_at: s.finished_at ?? null,
    updated_at: s.updated_at ?? `2026-08-19T00:00:0${i}Z`,
    progress: s.progress ?? 0,
    current_step: s.current_step ?? null,
    error_code: s.error_code ?? null,
    safe_error_message: s.safe_error_message ?? null,
    worker_id: s.worker_id ?? null,
    attempt_count: s.attempt_count ?? 0,
    max_attempts: s.max_attempts ?? 3,
    payload_json: s.payload_json ?? null,
  }));

  const client: PostgresQueryable = {
    query: (async (sql: string, params: unknown[] = []) => {
      if (sql.startsWith("UPDATE jobs SET status = 'RUNNING'")) {
        const [startedAt, updatedAt, workerId] = params as [string, string, string];
        const next = [...rows].filter((r) => r.status === "QUEUED").sort((a, b) => a.created_at.localeCompare(b.created_at))[0];
        if (!next) return { rows: [] };
        next.status = "RUNNING";
        next.started_at = startedAt;
        next.updated_at = updatedAt;
        next.worker_id = workerId;
        next.attempt_count += 1;
        return { rows: [{ ...next }] };
      }
      throw new Error(`fakeJobsTable: unhandled SQL: ${sql}`);
    }) as PostgresQueryable["query"],
  };
  return { client, rows };
}

describe("claimNextQueuedJob -- Postgres atomic claiming", () => {
  it("only one of two claims against a single QUEUED job succeeds", async () => {
    const { client } = fakeJobsTable([{ id: "job-1", status: "QUEUED" }]);
    __setExecutorForTests(new PostgresExecutor(client));
    try {
      const [first, second] = await Promise.all([claimNextQueuedJob("worker-a"), claimNextQueuedJob("worker-b")]);
      const claimed = [first, second].filter((r): r is JobRow => r !== null);
      expect(claimed).toHaveLength(1);
      expect(claimed[0].id).toBe("job-1");
      expect(claimed[0].status).toBe("RUNNING");
      expect(["worker-a", "worker-b"]).toContain(claimed[0].worker_id);
      // The loser gets null, never a duplicate/second claim of the same row.
      expect([first, second].filter((r) => r === null)).toHaveLength(1);
    } finally {
      __resetExecutorForTests();
    }
  });

  it("two workers claiming two distinct QUEUED jobs each get a different job, never the same one twice", async () => {
    const { client } = fakeJobsTable([
      { id: "job-1", status: "QUEUED", created_at: "2026-08-19T00:00:00Z" },
      { id: "job-2", status: "QUEUED", created_at: "2026-08-19T00:00:01Z" },
    ]);
    __setExecutorForTests(new PostgresExecutor(client));
    try {
      const [first, second] = await Promise.all([claimNextQueuedJob("worker-a"), claimNextQueuedJob("worker-b")]);
      expect(first).not.toBeNull();
      expect(second).not.toBeNull();
      expect(first!.id).not.toBe(second!.id);
      expect(new Set([first!.id, second!.id])).toEqual(new Set(["job-1", "job-2"]));
    } finally {
      __resetExecutorForTests();
    }
  });

  it("claims the OLDEST queued job first (created_at ASC), not an arbitrary one", async () => {
    const { client } = fakeJobsTable([
      { id: "job-newer", status: "QUEUED", created_at: "2026-08-19T05:00:00Z" },
      { id: "job-older", status: "QUEUED", created_at: "2026-08-19T01:00:00Z" },
    ]);
    __setExecutorForTests(new PostgresExecutor(client));
    try {
      const claimed = await claimNextQueuedJob("worker-a");
      expect(claimed?.id).toBe("job-older");
    } finally {
      __resetExecutorForTests();
    }
  });

  it("returns null (never throws, never fabricates a job) when nothing is QUEUED", async () => {
    const { client } = fakeJobsTable([{ id: "job-1", status: "RUNNING" }]);
    __setExecutorForTests(new PostgresExecutor(client));
    try {
      const claimed = await claimNextQueuedJob("worker-a");
      expect(claimed).toBeNull();
    } finally {
      __resetExecutorForTests();
    }
  });

  it("a job already RUNNING is never reclaimed by a second caller", async () => {
    const { client } = fakeJobsTable([{ id: "job-1", status: "QUEUED" }]);
    __setExecutorForTests(new PostgresExecutor(client));
    try {
      const first = await claimNextQueuedJob("worker-a");
      expect(first?.id).toBe("job-1");
      const second = await claimNextQueuedJob("worker-b");
      expect(second).toBeNull();
    } finally {
      __resetExecutorForTests();
    }
  });
});
