// Milestone 30: standalone job-worker poll loop -- the WORKER service in
// DEPLOYMENT.md's service topology, separate from the WEB (Next.js)
// service. Polls the `jobs` table (lib/jobs/queue.ts) and executes
// whatever is claimed via lib/jobs/worker.ts::runOneQueuedJob, exactly
// the same execution path the admin Process/Refresh routes already run
// inline for local dev / a single-instance deployment.
//
// Not required for local development (the routes run jobs inline without
// this) -- this script exists so a real hosted deployment CAN split web
// and worker into separate processes/services once that's actually
// wanted, without any different job-execution code path. Run with:
//
//   node scripts/run-job-worker.ts
//
// SCOPE NOTE: this has been exercised as a standalone process against
// the local SQLite database during this milestone's development, but
// NOT against a real multi-process/multi-machine Postgres deployment --
// see lib/jobs/queue.ts::claimNextQueuedJob's docstring for what genuine
// multi-worker concurrency safety would still need (row-level locking),
// and DEPLOYMENT.md for the honest "not yet validated" note.

import { ensureSlateJobHandlersRegistered } from "../lib/jobs/slateJobHandlers.ts";
import { recordHeartbeat } from "../lib/jobs/heartbeat.ts";
import { runOneQueuedJob } from "../lib/jobs/worker.ts";

const WORKER_ID = process.env.WORKER_ID || `worker-${process.pid}`;
const POLL_INTERVAL_MS = Number(process.env.JOB_WORKER_POLL_INTERVAL_MS) || 5000;
const HEARTBEAT_INTERVAL_MS = 15_000;

let stopping = false;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function main() {
  ensureSlateJobHandlersRegistered();
  console.log(`[job-worker] ${WORKER_ID} starting, polling every ${POLL_INTERVAL_MS}ms`);
  await recordHeartbeat(WORKER_ID, { startedAt: new Date().toISOString() });

  let lastHeartbeat = Date.now();

  while (!stopping) {
    const result = await runOneQueuedJob(WORKER_ID);
    if (result.status === "NO_JOB") {
      if (Date.now() - lastHeartbeat > HEARTBEAT_INTERVAL_MS) {
        await recordHeartbeat(WORKER_ID);
        lastHeartbeat = Date.now();
      }
      await sleep(POLL_INTERVAL_MS);
      continue;
    }
    console.log(`[job-worker] job ${result.job?.id} (${result.job?.job_type}) -> ${result.status}`);
    lastHeartbeat = Date.now();
  }
}

process.on("SIGTERM", () => {
  stopping = true;
});
process.on("SIGINT", () => {
  stopping = true;
});

main().catch((err) => {
  console.error("[job-worker] fatal error:", err instanceof Error ? err.message : String(err));
  process.exitCode = 1;
});
