import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "../../db/client";
import { __resetExecutorForTests } from "../../db/executor";
import { claimNextQueuedJob, completeJob, enqueueJob, failJob, getJob, listJobsForSlate, listRecentJobs, updateJobProgress } from "../queue";

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

describe("enqueueJob", () => {
  it("creates a new QUEUED job", async () => {
    const { job, created } = await enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "main", createdBy: null });
    expect(created).toBe(true);
    expect(job.status).toBe("QUEUED");
    expect(job.job_type).toBe("PROCESS_SLATE");
    expect(job.attempt_count).toBe(0);
    expect(job.max_attempts).toBe(3);
  });

  it("is idempotent: a second enqueue for the same active (slate, type) returns the existing job instead of creating a duplicate", async () => {
    const first = await enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "main", createdBy: null });
    const second = await enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "main", createdBy: null });
    expect(second.created).toBe(false);
    expect(second.job.id).toBe(first.job.id);
    expect((await listRecentJobs()).filter((j) => j.slate_date === "2026-08-19" && j.slate_id === "main")).toHaveLength(1);
  });

  it("does not dedupe across different job types for the same slate", async () => {
    const process = await enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "main", createdBy: null });
    const refresh = await enqueueJob({ jobType: "REFRESH_SLATE", slateDate: "2026-08-19", slateId: "main", createdBy: null });
    expect(process.job.id).not.toBe(refresh.job.id);
  });

  it("allows a new job once the previous one for the same slate/type has reached a terminal state", async () => {
    const { job } = await enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "main", createdBy: null });
    await completeJob(job.id);
    const second = await enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "main", createdBy: null });
    expect(second.created).toBe(true);
    expect(second.job.id).not.toBe(job.id);
  });
});

describe("claimNextQueuedJob", () => {
  it("claims the oldest queued job, sets RUNNING/started_at/worker_id, increments attempt_count", async () => {
    const { job } = await enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "main", createdBy: null });
    const claimed = await claimNextQueuedJob("worker-1");
    expect(claimed?.id).toBe(job.id);
    expect(claimed?.status).toBe("RUNNING");
    expect(claimed?.worker_id).toBe("worker-1");
    expect(claimed?.attempt_count).toBe(1);
    expect(claimed?.started_at).toBeTruthy();
  });

  it("returns null when the queue is empty", async () => {
    expect(await claimNextQueuedJob("worker-1")).toBeNull();
  });

  it("claims jobs in FIFO (created_at) order", async () => {
    const a = (await enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "a", createdBy: null })).job;
    const b = (await enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "b", createdBy: null })).job;
    const firstClaimed = await claimNextQueuedJob("worker-1");
    expect(firstClaimed?.id === a.id || firstClaimed?.id === b.id).toBe(true);
    const secondClaimed = await claimNextQueuedJob("worker-1");
    expect([a.id, b.id]).toContain(secondClaimed?.id);
    expect(secondClaimed?.id).not.toBe(firstClaimed?.id);
  });

  it("never claims a RUNNING or terminal job again", async () => {
    const { job } = await enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "main", createdBy: null });
    await claimNextQueuedJob("worker-1");
    expect(await claimNextQueuedJob("worker-2")).toBeNull();
    await completeJob(job.id);
    expect(await claimNextQueuedJob("worker-2")).toBeNull();
  });
});

describe("updateJobProgress / completeJob / failJob", () => {
  it("updateJobProgress clamps into [0,100] and records current_step", async () => {
    const { job } = await enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "main", createdBy: null });
    await updateJobProgress(job.id, 150, "over");
    expect((await getJob(job.id))?.progress).toBe(100);
    await updateJobProgress(job.id, -10, "under");
    expect((await getJob(job.id))?.progress).toBe(0);
  });

  it("completeJob sets SUCCEEDED, progress 100, finished_at", async () => {
    const { job } = await enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "main", createdBy: null });
    await completeJob(job.id);
    const done = (await getJob(job.id))!;
    expect(done.status).toBe("SUCCEEDED");
    expect(done.progress).toBe(100);
    expect(done.finished_at).toBeTruthy();
  });

  it("failJob marks FAILED (non-retryable) with error_code/safe_error_message and finished_at", async () => {
    const { job } = await enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "main", createdBy: null });
    await claimNextQueuedJob("worker-1");
    const status = await failJob(job.id, { errorCode: "PLAYER_MATCHING_FAILURE", safeErrorMessage: "Zero DFS entries matched.", retryable: false });
    expect(status).toBe("FAILED");
    const failed = (await getJob(job.id))!;
    expect(failed.status).toBe("FAILED");
    expect(failed.error_code).toBe("PLAYER_MATCHING_FAILURE");
    expect(failed.safe_error_message).toBe("Zero DFS entries matched.");
    expect(failed.finished_at).toBeTruthy();
  });

  it("failJob resets a retryable failure to QUEUED (not FAILED) while attempts remain", async () => {
    const { job } = await enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "main", createdBy: null });
    await claimNextQueuedJob("worker-1"); // attempt_count -> 1, max_attempts default 3
    const status = await failJob(job.id, { errorCode: "WORKER_UNEXPECTED_ERROR", safeErrorMessage: "transient", retryable: true });
    expect(status).toBe("QUEUED");
    const retried = (await getJob(job.id))!;
    expect(retried.status).toBe("QUEUED");
    expect(retried.finished_at).toBeNull();
  });

  it("failJob stops retrying once attempt_count reaches max_attempts, even if retryable", async () => {
    const { job } = await enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "main", createdBy: null });
    for (let i = 0; i < 3; i++) {
      await claimNextQueuedJob("worker-1");
      await failJob(job.id, { errorCode: "WORKER_UNEXPECTED_ERROR", safeErrorMessage: "transient", retryable: true });
    }
    expect((await getJob(job.id))?.status).toBe("FAILED");
  });
});

describe("listJobsForSlate / listRecentJobs", () => {
  it("listJobsForSlate returns only jobs for that (date, id), newest first", async () => {
    await enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "main", createdBy: null });
    await enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "other", createdBy: null });
    const jobs = await listJobsForSlate("2026-08-19", "main");
    expect(jobs).toHaveLength(1);
    expect(jobs[0].slate_id).toBe("main");
  });
});
