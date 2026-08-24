import { beforeEach, describe, expect, it, vi } from "vitest";

const cookieStore = new Map<string, string>();
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) => (cookieStore.has(name) ? { name, value: cookieStore.get(name)! } : undefined),
    set: (name: string, value: string) => {
      cookieStore.set(name, value);
    },
    delete: (name: string) => {
      cookieStore.delete(name);
    },
  }),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser, updateUserRole, findUserById } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { insertSubscription, getCurrentSubscriptionForUser } = await import("@/lib/db/subscriptions");
const { createSession, findSessionByRawToken } = await import("@/lib/db/sessions");
const { listUserEntitlements } = await import("@/lib/db/entitlements");
const { listAuditLog } = await import("@/lib/db/auditLog");
const { GET: listUsers } = await import("../route");
const { GET: getUser, PATCH: patchUser } = await import("../[id]/route");
const { POST: grantEntitlement, DELETE: revokeEntitlement } = await import("../[id]/entitlements/route");

function ctx(id: string) {
  return { params: Promise.resolve({ id }) };
}

function jsonRequest(url: string, body: unknown, method = "PATCH") {
  return new Request(url, { method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
}

async function loginAsAdmin() {
  const admin = await createUser({ email: "admin@example.com", passwordHash: "h" });
  await updateUserRole(admin.id, "ADMIN");
  await establishSession(admin.id, null);
  return admin;
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
});

describe("GET /api/admin/users", () => {
  it("401s with no session", async () => {
    const res = await listUsers(new Request("http://localhost/api/admin/users"));
    expect(res.status).toBe(401);
  });

  it("403s for a logged-in MEMBER", async () => {
    const member = await createUser({ email: "member@example.com", passwordHash: "h" });
    await establishSession(member.id, null);
    const res = await listUsers(new Request("http://localhost/api/admin/users"));
    expect(res.status).toBe(403);
  });

  it("lists users for an ADMIN, applying query-string filters", async () => {
    await loginAsAdmin();
    await createUser({ email: "target@example.com", passwordHash: "h" });

    const res = await listUsers(new Request("http://localhost/api/admin/users?search=target"));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.total).toBe(1);
    expect(body.users[0].email).toBe("target@example.com");
  });
});

describe("GET /api/admin/users/[id]", () => {
  it("401s with no session", async () => {
    const res = await getUser(new Request("http://localhost/api/admin/users/x"), ctx("x"));
    expect(res.status).toBe(401);
  });

  it("403s for a MEMBER", async () => {
    const member = await createUser({ email: "m2@example.com", passwordHash: "h" });
    await establishSession(member.id, null);
    const res = await getUser(new Request("http://localhost/api/admin/users/x"), ctx("x"));
    expect(res.status).toBe(403);
  });

  it("404s for an unknown user id", async () => {
    await loginAsAdmin();
    const res = await getUser(new Request("http://localhost/api/admin/users/nope"), ctx("nope"));
    expect(res.status).toBe(404);
  });

  it("returns user + subscription + entitlements for a real user", async () => {
    await loginAsAdmin();
    const target = await createUser({ email: "detail@example.com", passwordHash: "h" });
    await insertSubscription({ userId: target.id, planId: "weekly", status: "trialing" });

    const res = await getUser(new Request("http://localhost/api/admin/users/x"), ctx(target.id));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.user.email).toBe("detail@example.com");
    expect(body.subscription.status).toBe("trialing");
    expect(body.entitlements).toEqual([]);
  });
});

describe("PATCH /api/admin/users/[id] -- change_role", () => {
  it("promotes a MEMBER to ADMIN and writes an audit row", async () => {
    const admin = await loginAsAdmin();
    const target = await createUser({ email: "promote@example.com", passwordHash: "h" });

    const res = await patchUser(
      jsonRequest(`http://localhost/api/admin/users/${target.id}`, { action: "change_role", role: "ADMIN" }),
      ctx(target.id),
    );
    expect(res.status).toBe(200);
    expect((await findUserById(target.id))?.role).toBe("ADMIN");
    const entries = await listAuditLog({ action: "user_role_changed" });
    expect(entries).toHaveLength(1);
    expect(entries[0].actor_user_id).toBe(admin.id);
    expect(entries[0].target_id).toBe(target.id);
  });

  it("blocks a MEMBER from self-promoting to ADMIN via this same endpoint (privilege escalation)", async () => {
    const member = await createUser({ email: "wannabe@example.com", passwordHash: "h" });
    await establishSession(member.id, null);

    const res = await patchUser(
      jsonRequest(`http://localhost/api/admin/users/${member.id}`, { action: "change_role", role: "ADMIN" }),
      ctx(member.id),
    );
    expect(res.status).toBe(403);
    expect((await findUserById(member.id))?.role).toBe("MEMBER");
  });

  it("refuses to demote the last remaining admin (privilege-escalation-adjacent safety rail)", async () => {
    const admin = await loginAsAdmin();
    const res = await patchUser(
      jsonRequest(`http://localhost/api/admin/users/${admin.id}`, { action: "change_role", role: "MEMBER" }),
      ctx(admin.id),
    );
    expect(res.status).toBe(400);
    expect((await findUserById(admin.id))?.role).toBe("ADMIN");
  });

  it("400s for an invalid role value", async () => {
    await loginAsAdmin();
    const target = await createUser({ email: "badrole@example.com", passwordHash: "h" });
    const res = await patchUser(
      jsonRequest(`http://localhost/api/admin/users/${target.id}`, { action: "change_role", role: "SUPERUSER" }),
      ctx(target.id),
    );
    expect(res.status).toBe(400);
  });
});

describe("PATCH /api/admin/users/[id] -- disable_account / restore_account", () => {
  it("disables the account and kills their existing sessions", async () => {
    await loginAsAdmin();
    const target = await createUser({ email: "disableme@example.com", passwordHash: "h" });
    // A raw DB session row (not routed through the shared cookie store,
    // which is already occupied by the admin's own session in this test).
    const { rawToken } = await createSession(target.id, null);
    expect(await findSessionByRawToken(rawToken)).not.toBeNull();

    const res = await patchUser(
      jsonRequest(`http://localhost/api/admin/users/${target.id}`, { action: "disable_account" }),
      ctx(target.id),
    );
    expect(res.status).toBe(200);
    expect((await findUserById(target.id))?.disabled_at).not.toBeNull();
    expect(await findSessionByRawToken(rawToken)).toBeNull();

    const restoreRes = await patchUser(
      jsonRequest(`http://localhost/api/admin/users/${target.id}`, { action: "restore_account" }),
      ctx(target.id),
    );
    expect(restoreRes.status).toBe(200);
    expect((await findUserById(target.id))?.disabled_at).toBeNull();
  });
});

describe("PATCH /api/admin/users/[id] -- grant_beta_access / revoke_beta_access", () => {
  it("grants beta access, recording who granted it, then revokes it", async () => {
    const admin = await loginAsAdmin();
    const target = await createUser({ email: "beta-target@example.com", passwordHash: "h" });

    const grantRes = await patchUser(
      jsonRequest(`http://localhost/api/admin/users/${target.id}`, { action: "grant_beta_access" }),
      ctx(target.id),
    );
    expect(grantRes.status).toBe(200);
    let reloaded = (await findUserById(target.id))!;
    expect(reloaded.beta_access_granted_at).not.toBeNull();
    expect(reloaded.beta_access_granted_by).toBe(admin.id);
    expect(await listAuditLog({ action: "user_beta_access_granted" })).toHaveLength(1);

    const revokeRes = await patchUser(
      jsonRequest(`http://localhost/api/admin/users/${target.id}`, { action: "revoke_beta_access" }),
      ctx(target.id),
    );
    expect(revokeRes.status).toBe(200);
    reloaded = (await findUserById(target.id))!;
    expect(reloaded.beta_access_granted_at).toBeNull();
    expect(reloaded.beta_access_granted_by).toBeNull();
    expect(await listAuditLog({ action: "user_beta_access_revoked" })).toHaveLength(1);
  });
});

describe("PATCH /api/admin/users/[id] -- extend_trial", () => {
  it("400s when the user has no subscription", async () => {
    await loginAsAdmin();
    const target = await createUser({ email: "notrial@example.com", passwordHash: "h" });
    const res = await patchUser(
      jsonRequest(`http://localhost/api/admin/users/${target.id}`, { action: "extend_trial", days: 3 }),
      ctx(target.id),
    );
    expect(res.status).toBe(400);
  });

  it("extends an existing trial forward from its current expiry", async () => {
    await loginAsAdmin();
    const target = await createUser({ email: "extend@example.com", passwordHash: "h" });
    await insertSubscription({
      userId: target.id,
      planId: "weekly",
      status: "trialing",
      trialEndsAt: "2099-01-01T00:00:00.000Z",
    });

    const res = await patchUser(
      jsonRequest(`http://localhost/api/admin/users/${target.id}`, { action: "extend_trial", days: 3 }),
      ctx(target.id),
    );
    expect(res.status).toBe(200);
    const sub = await getCurrentSubscriptionForUser(target.id);
    expect(sub?.trial_ends_at).toBe("2099-01-04T00:00:00.000Z");
  });

  it("rejects an out-of-range days value", async () => {
    await loginAsAdmin();
    const target = await createUser({ email: "toobig@example.com", passwordHash: "h" });
    await insertSubscription({ userId: target.id, planId: "weekly", status: "trialing" });
    const res = await patchUser(
      jsonRequest(`http://localhost/api/admin/users/${target.id}`, { action: "extend_trial", days: 9999 }),
      ctx(target.id),
    );
    expect(res.status).toBe(400);
  });
});

describe("PATCH /api/admin/users/[id] -- grant_complimentary / remove_complimentary", () => {
  it("grants complimentary access on an unknown plan -> 400", async () => {
    await loginAsAdmin();
    const target = await createUser({ email: "comp1@example.com", passwordHash: "h" });
    const res = await patchUser(
      jsonRequest(`http://localhost/api/admin/users/${target.id}`, { action: "grant_complimentary", planId: "nope" }),
      ctx(target.id),
    );
    expect(res.status).toBe(400);
  });

  it("grants and then removes complimentary access", async () => {
    await loginAsAdmin();
    const target = await createUser({ email: "comp2@example.com", passwordHash: "h" });

    const grantRes = await patchUser(
      jsonRequest(`http://localhost/api/admin/users/${target.id}`, { action: "grant_complimentary", planId: "monthly" }),
      ctx(target.id),
    );
    expect(grantRes.status).toBe(200);
    expect((await getCurrentSubscriptionForUser(target.id))?.status).toBe("complimentary");

    const removeRes = await patchUser(
      jsonRequest(`http://localhost/api/admin/users/${target.id}`, { action: "remove_complimentary" }),
      ctx(target.id),
    );
    expect(removeRes.status).toBe(200);
    expect((await getCurrentSubscriptionForUser(target.id))?.status).toBe("canceled");
  });

  it("400s removing complimentary when none is active", async () => {
    await loginAsAdmin();
    const target = await createUser({ email: "comp3@example.com", passwordHash: "h" });
    const res = await patchUser(
      jsonRequest(`http://localhost/api/admin/users/${target.id}`, { action: "remove_complimentary" }),
      ctx(target.id),
    );
    expect(res.status).toBe(400);
  });
});

describe("PATCH /api/admin/users/[id] -- unknown action", () => {
  it("400s", async () => {
    await loginAsAdmin();
    const target = await createUser({ email: "unknown@example.com", passwordHash: "h" });
    const res = await patchUser(
      jsonRequest(`http://localhost/api/admin/users/${target.id}`, { action: "delete_everything" }),
      ctx(target.id),
    );
    expect(res.status).toBe(400);
  });
});

describe("POST/DELETE /api/admin/users/[id]/entitlements", () => {
  it("401s with no session", async () => {
    const res = await grantEntitlement(jsonRequest("http://localhost/x", { entitlementKey: "mlb.optimizer" }, "POST"), ctx("x"));
    expect(res.status).toBe(401);
  });

  it("403s for a MEMBER", async () => {
    const member = await createUser({ email: "m3@example.com", passwordHash: "h" });
    await establishSession(member.id, null);
    const res = await grantEntitlement(
      jsonRequest("http://localhost/x", { entitlementKey: "mlb.optimizer" }, "POST"),
      ctx("x"),
    );
    expect(res.status).toBe(403);
  });

  it("400s for an unknown entitlement key", async () => {
    await loginAsAdmin();
    const target = await createUser({ email: "ent1@example.com", passwordHash: "h" });
    const res = await grantEntitlement(
      jsonRequest(`http://localhost/x`, { entitlementKey: "not.a.real.key" }, "POST"),
      ctx(target.id),
    );
    expect(res.status).toBe(400);
  });

  it("grants and then revokes an entitlement, both writing audit rows", async () => {
    await loginAsAdmin();
    const target = await createUser({ email: "ent2@example.com", passwordHash: "h" });

    const grantRes = await grantEntitlement(
      jsonRequest(`http://localhost/x`, { entitlementKey: "mlb.optimizer", reason: "beta tester" }, "POST"),
      ctx(target.id),
    );
    expect(grantRes.status).toBe(200);
    expect((await listUserEntitlements(target.id)).map((e) => e.entitlement_key)).toContain("mlb.optimizer");

    const revokeRes = await revokeEntitlement(
      new Request(`http://localhost/x?entitlementKey=mlb.optimizer`, { method: "DELETE" }),
      ctx(target.id),
    );
    expect(revokeRes.status).toBe(200);
    expect(await listUserEntitlements(target.id)).toHaveLength(0);

    expect(await listAuditLog({ action: "user_entitlement_granted" })).toHaveLength(1);
    expect(await listAuditLog({ action: "user_entitlement_revoked" })).toHaveLength(1);
  });
});
