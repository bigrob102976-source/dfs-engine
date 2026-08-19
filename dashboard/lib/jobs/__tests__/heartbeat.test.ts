import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "../../db/client";
import { deriveWorkerHealth, isAnyWorkerOnline, listWorkerHealth, recordHeartbeat } from "../heartbeat";

beforeEach(() => {
  __resetDbForTests();
});

describe("deriveWorkerHealth", () => {
  const now = new Date("2026-08-19T12:00:00.000Z");

  it("ONLINE within the online threshold", () => {
    expect(deriveWorkerHealth("2026-08-19T11:59:45.000Z", now)).toBe("ONLINE"); // 15s ago
  });

  it("STALE between the online and stale thresholds", () => {
    expect(deriveWorkerHealth("2026-08-19T11:59:00.000Z", now)).toBe("STALE"); // 60s ago
  });

  it("OFFLINE beyond the stale threshold", () => {
    expect(deriveWorkerHealth("2026-08-19T11:55:00.000Z", now)).toBe("OFFLINE"); // 5min ago
  });
});

describe("recordHeartbeat / listWorkerHealth", () => {
  it("upserts by worker_id and reports ONLINE for a fresh heartbeat", () => {
    recordHeartbeat("worker-1", { note: "first" });
    const health = listWorkerHealth();
    expect(health).toHaveLength(1);
    expect(health[0].workerId).toBe("worker-1");
    expect(health[0].health).toBe("ONLINE");
  });

  it("a second heartbeat for the same worker_id updates the row rather than inserting a second one", () => {
    recordHeartbeat("worker-1");
    recordHeartbeat("worker-1");
    expect(listWorkerHealth()).toHaveLength(1);
  });

  it("isAnyWorkerOnline is false with no heartbeats and true after one", () => {
    expect(isAnyWorkerOnline()).toBe(false);
    recordHeartbeat("worker-1");
    expect(isAnyWorkerOnline()).toBe(true);
  });
});
