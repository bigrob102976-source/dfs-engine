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

// next/navigation's real redirect() throws a special NEXT_REDIRECT error
// that Next's rendering machinery intercepts -- outside a real request
// we fake the same "throws with the destination attached" contract so
// guards.ts's redirect() calls are observable in a plain test.
vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new Error(`NEXT_REDIRECT:${url}`);
  },
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("../session");
const { requireAuth, requireAdmin, requireAuthApi, requireAdminApi } = await import("../guards");
const { NextResponse } = await import("next/server");

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
});

describe("requireAuth (Server Component / layout guard)", () => {
  it("redirects to /login when logged out", async () => {
    await expect(requireAuth()).rejects.toThrow("NEXT_REDIRECT:/login");
  });

  it("redirects to /login?next=... when a nextPath is given", async () => {
    await expect(requireAuth("/dashboard/optimizer")).rejects.toThrow(
      "NEXT_REDIRECT:/login?next=%2Fdashboard%2Foptimizer",
    );
  });

  it("returns the current user when logged in", async () => {
    const user = await createUser({ email: "member@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    const result = await requireAuth();
    expect(result.id).toBe(user.id);
  });
});

describe("requireAdmin (Server Component / layout guard)", () => {
  it("redirects to /login when logged out (not /dashboard -- auth check comes first)", async () => {
    await expect(requireAdmin()).rejects.toThrow("NEXT_REDIRECT:/login");
  });

  it("redirects a logged-in MEMBER to /dashboard (privilege escalation via direct nav is blocked)", async () => {
    const user = await createUser({ email: "member2@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    await expect(requireAdmin()).rejects.toThrow("NEXT_REDIRECT:/dashboard");
  });

  it("allows a real ADMIN through", async () => {
    const user = await createUser({ email: "admin@example.com", passwordHash: "h" });
    await updateUserRole(user.id, "ADMIN");
    await establishSession(user.id, null);
    const result = await requireAdmin();
    expect(result.role).toBe("ADMIN");
  });

  it("re-checks role fresh from the DB even if it changed after the session was established", async () => {
    const user = await createUser({ email: "promoted@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    await expect(requireAdmin()).rejects.toThrow("NEXT_REDIRECT:/dashboard");

    await updateUserRole(user.id, "ADMIN");
    const result = await requireAdmin();
    expect(result.role).toBe("ADMIN");
  });
});

describe("requireAuthApi (API route guard)", () => {
  it("returns a 401 NextResponse when logged out", async () => {
    const result = await requireAuthApi();
    expect(result).toBeInstanceOf(NextResponse);
    expect((result as InstanceType<typeof NextResponse>).status).toBe(401);
  });

  it("returns the current user when logged in", async () => {
    const user = await createUser({ email: "apiuser@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    const result = await requireAuthApi();
    expect(result).not.toBeInstanceOf(NextResponse);
  });
});

describe("requireAdminApi (API route guard)", () => {
  it("returns a 401 NextResponse when logged out", async () => {
    const result = await requireAdminApi();
    expect(result).toBeInstanceOf(NextResponse);
    expect((result as InstanceType<typeof NextResponse>).status).toBe(401);
  });

  it("returns a 403 NextResponse for a logged-in MEMBER (no client-side role can bypass this)", async () => {
    const user = await createUser({ email: "apimember@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    const result = await requireAdminApi();
    expect(result).toBeInstanceOf(NextResponse);
    expect((result as InstanceType<typeof NextResponse>).status).toBe(403);
  });

  it("returns the current user for a real ADMIN", async () => {
    const user = await createUser({ email: "apiadmin@example.com", passwordHash: "h" });
    await updateUserRole(user.id, "ADMIN");
    await establishSession(user.id, null);
    const result = await requireAdminApi();
    expect(result).not.toBeInstanceOf(NextResponse);
  });
});
