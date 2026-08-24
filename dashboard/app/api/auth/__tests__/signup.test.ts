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
const { findUserByEmail } = await import("@/lib/db/users");
const { getCurrentUser } = await import("@/lib/auth/session");
const { POST } = await import("../signup/route");

function jsonRequest(body: unknown) {
  return new Request("http://localhost/api/auth/signup", {
    method: "POST",
    headers: { "content-type": "application/json", "user-agent": "vitest" },
    body: JSON.stringify(body),
  });
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
});

describe("POST /api/auth/signup", () => {
  it("400s on a malformed JSON body", async () => {
    const res = await POST(new Request("http://localhost/api/auth/signup", { method: "POST", body: "not json" }));
    expect(res.status).toBe(400);
  });

  it("400s on an invalid email", async () => {
    const res = await POST(jsonRequest({ email: "not-an-email", password: "longenough123" }));
    expect(res.status).toBe(400);
  });

  it("400s on a too-short password", async () => {
    const res = await POST(jsonRequest({ email: "short@example.com", password: "short" }));
    expect(res.status).toBe(400);
  });

  it("creates the user, signs them in, and returns a dev verification link", async () => {
    const res = await POST(jsonRequest({ email: "new@example.com", password: "longenough123" }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.ok).toBe(true);
    expect(body.devVerificationLink).toContain("/verify-email?token=");

    expect(findUserByEmail("new@example.com")).not.toBeNull();
    expect((await getCurrentUser())?.email).toBe("new@example.com");
  });

  it("409s on a duplicate email", async () => {
    await POST(jsonRequest({ email: "dupe@example.com", password: "longenough123" }));
    cookieStore.clear(); // simulate a fresh, logged-out attempt
    const res = await POST(jsonRequest({ email: "dupe@example.com", password: "anotherpass123" }));
    expect(res.status).toBe(409);
  });

  it("normalizes email case for duplicate detection", async () => {
    await POST(jsonRequest({ email: "Case@Example.com", password: "longenough123" }));
    cookieStore.clear();
    const res = await POST(jsonRequest({ email: "case@example.com", password: "longenough123" }));
    expect(res.status).toBe(409);
  });
});
