import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "../client";
import { computeDbStats } from "../systemStats";
import { insertSubscription } from "../subscriptions";
import { createUser } from "../users";
import { createSession } from "../sessions";
import { recordAuditLog } from "../auditLog";

beforeEach(() => {
  __resetDbForTests();
});

describe("computeDbStats", () => {
  it("returns real zero counts on an empty database", () => {
    expect(computeDbStats()).toEqual({ totalUsers: 0, totalSessions: 0, totalSubscriptions: 0, totalAuditLogEntries: 0 });
  });

  it("reflects real inserted rows", () => {
    const user = createUser({ email: "stats@example.com", passwordHash: "h" });
    createSession(user.id, null);
    insertSubscription({ userId: user.id, planId: "weekly", status: "active" });
    recordAuditLog({ actorUserId: null, actorLabel: "system", action: "test_action" });

    const stats = computeDbStats();
    expect(stats.totalUsers).toBe(1);
    expect(stats.totalSessions).toBe(1);
    expect(stats.totalSubscriptions).toBe(1);
    expect(stats.totalAuditLogEntries).toBe(1);
  });
});
