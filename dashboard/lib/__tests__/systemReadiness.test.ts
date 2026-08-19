import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "../db/client";
import { enqueueJob } from "../jobs/queue";
import { recordHeartbeat } from "../jobs/heartbeat";
import { getDatabaseReadiness, getJobQueueReadiness, getObjectStorageReadiness, getWorkerReadiness } from "../systemReadiness";

const ENV_KEYS = ["OBJECT_STORAGE_ENDPOINT", "OBJECT_STORAGE_REGION", "OBJECT_STORAGE_BUCKET", "OBJECT_STORAGE_ACCESS_KEY", "OBJECT_STORAGE_SECRET_KEY"] as const;

beforeEach(() => {
  __resetDbForTests();
  for (const k of ENV_KEYS) delete (process.env as Record<string, string | undefined>)[k];
});

describe("getDatabaseReadiness", () => {
  it("reports CONNECTED for local SQLite in development", async () => {
    const readiness = await getDatabaseReadiness();
    expect(readiness).toEqual({ kind: "sqlite", status: "CONNECTED", detail: expect.any(String) });
  });
});

describe("getObjectStorageReadiness", () => {
  it("reports NOT_CONFIGURED when no OBJECT_STORAGE_* vars are set", async () => {
    const readiness = await getObjectStorageReadiness();
    expect(readiness.status).toBe("NOT_CONFIGURED");
    expect(readiness.detail).toContain("OBJECT_STORAGE_REGION");
  });

  it("reports ERROR (not a thrown exception) when configured but unreachable", async () => {
    (process.env as Record<string, string | undefined>).OBJECT_STORAGE_REGION = "auto";
    (process.env as Record<string, string | undefined>).OBJECT_STORAGE_BUCKET = "does-not-exist-bucket-xyz";
    (process.env as Record<string, string | undefined>).OBJECT_STORAGE_ACCESS_KEY = "ak";
    (process.env as Record<string, string | undefined>).OBJECT_STORAGE_SECRET_KEY = "sk";
    (process.env as Record<string, string | undefined>).OBJECT_STORAGE_ENDPOINT = "https://127.0.0.1:1/unreachable";
    const readiness = await getObjectStorageReadiness();
    expect(readiness.status).toBe("ERROR");
    expect(readiness.detail).toBeTruthy();
  }, 15000);
});

describe("getJobQueueReadiness", () => {
  it("reports CONNECTED with accurate queued/running counts", () => {
    enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "a", createdBy: null });
    enqueueJob({ jobType: "PROCESS_SLATE", slateDate: "2026-08-19", slateId: "b", createdBy: null });
    const readiness = getJobQueueReadiness();
    expect(readiness.status).toBe("CONNECTED");
    expect(readiness.queuedCount).toBe(2);
    expect(readiness.runningCount).toBe(0);
  });
});

describe("getWorkerReadiness", () => {
  it("reports OFFLINE with no heartbeats and ONLINE after one", () => {
    expect(getWorkerReadiness().status).toBe("OFFLINE");
    recordHeartbeat("worker-1");
    expect(getWorkerReadiness().status).toBe("ONLINE");
  });
});
