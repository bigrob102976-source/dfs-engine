import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "../client";
import { __resetExecutorForTests } from "../executor";
import { computeDbStats } from "../systemStats";
import { insertSubscription } from "../subscriptions";
import { createUser } from "../users";
import { createSession } from "../sessions";
import { recordAuditLog } from "../auditLog";

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

describe("computeDbStats", () => {
  it("returns real zero counts on an empty database", async () => {
    expect(await computeDbStats()).toEqual({ totalUsers: 0, totalSessions: 0, totalSubscriptions: 0, totalAuditLogEntries: 0 });
  });

  it("reflects real inserted rows", async () => {
    const user = await createUser({ email: "stats@example.com", passwordHash: "h" });
    await createSession(user.id, null);
    await insertSubscription({ userId: user.id, planId: "weekly", status: "active" });
    await recordAuditLog({ actorUserId: null, actorLabel: "system", action: "test_action" });

    const stats = await computeDbStats();
    expect(stats.totalUsers).toBe(1);
    expect(stats.totalSessions).toBe(1);
    expect(stats.totalSubscriptions).toBe(1);
    expect(stats.totalAuditLogEntries).toBe(1);
  });
});
