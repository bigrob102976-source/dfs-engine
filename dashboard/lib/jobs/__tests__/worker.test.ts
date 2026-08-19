import { beforeEach, describe, expect, it, vi } from "vitest";

import { __resetDbForTests } from "../../db/client";
import { enqueueJob, getJob } from "../queue";
import { listWorkerHealth } from "../heartbeat";
import { registerJobHandler, runOneQueuedJob, runOneQueuedJobInBackground, TransientJobError, type JobHandler } from "../worker";

beforeEach(() => {
  __resetDbForTests();
});

describe("runOneQueuedJob", () => {
  it("returns NO_JOB and touches nothing when the queue is empty", async () => {
    const result = await runOneQueuedJob("worker-1");
    expect(result).toEqual({ ran: false, job: null, status: "NO_JOB" });
  });

  it("claims a job, runs its registered handler, and marks it SUCCEEDED", async () => {
    const handler: JobHandler = vi.fn(async (_job, onProgress) => {
      onProgress(50, "halfway");
    });
    registerJobHandler("PROCESS_SLATE", handler);

    const { job } = enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "main", createdBy: null });
    const result = await runOneQueuedJob("worker-1");

    expect(result.status).toBe("SUCCEEDED");
    expect(handler).toHaveBeenCalledTimes(1);
    const finished = getJob(job.id)!;
    expect(finished.status).toBe("SUCCEEDED");
    expect(finished.progress).toBe(100);
  });

  it("records a heartbeat for the worker while it runs", async () => {
    registerJobHandler("PROCESS_SLATE", async () => {});
    enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "main", createdBy: null });
    await runOneQueuedJob("worker-heartbeat-test");
    expect(listWorkerHealth().some((w) => w.workerId === "worker-heartbeat-test")).toBe(true);
  });

  it("marks the job FAILED (not retryable by default) when the handler throws", async () => {
    registerJobHandler("PROCESS_SLATE", async () => {
      throw new Error("boom");
    });
    const { job } = enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "main", createdBy: null });
    const result = await runOneQueuedJob("worker-1");

    expect(result.status).toBe("FAILED");
    const failed = getJob(job.id)!;
    expect(failed.status).toBe("FAILED");
    expect(failed.safe_error_message).toBe("boom");
  });

  it("retries a TransientJobError (resets to QUEUED) while attempts remain, instead of failing outright", async () => {
    registerJobHandler("PROCESS_SLATE", async () => {
      throw new TransientJobError("temporary network blip");
    });
    const { job } = enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "main", createdBy: null });
    const result = await runOneQueuedJob("worker-1");

    expect(result.status).toBe("QUEUED");
    expect(getJob(job.id)?.status).toBe("QUEUED");
  });

  it("marks a job NO_HANDLER for a job type with no registered handler, without throwing", async () => {
    const { job } = enqueueJob({ jobType: "MODEL_EVALUATION", slateDate: null, slateId: null, createdBy: null });
    const result = await runOneQueuedJob("worker-1");

    expect(result.status).toBe("NO_HANDLER");
    const failed = getJob(job.id)!;
    expect(failed.status).toBe("FAILED");
    expect(failed.error_code).toBe("NO_HANDLER");
  });
});

describe("runOneQueuedJobInBackground", () => {
  it("does not throw synchronously even when the handler rejects", () => {
    registerJobHandler("PROCESS_SLATE", async () => {
      throw new Error("async boom");
    });
    enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "main", createdBy: null });
    expect(() => runOneQueuedJobInBackground("worker-1")).not.toThrow();
  });
});
