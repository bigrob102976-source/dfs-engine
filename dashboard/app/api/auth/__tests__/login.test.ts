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
const { hasAuditAction } = await import("@/lib/db/auditLog");
const { hashPassword } = await import("@/lib/auth/password");
const { createUser } = await import("@/lib/db/users");
const { getCurrentUser } = await import("@/lib/auth/session");
const { POST } = await import("../login/route");

const BOOTSTRAP_EMAIL = "bigrob102976@gmail.com";

function jsonRequest(body: unknown) {
  return new Request("http://localhost/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json", "user-agent": "vitest" },
    body: JSON.stringify(body),
  });
}

beforeEach(() => {
  __resetDbForTests();
  cookieStore.clear();
});

describe("POST /api/auth/login", () => {
  it("401s for an unknown email with the same generic message as a wrong password", async () => {
    const resUnknown = await POST(jsonRequest({ email: "nobody@example.com", password: "whatever123" }));
    expect(resUnknown.status).toBe(401);
    const bodyUnknown = await resUnknown.json();

    createUser({ email: "real@example.com", passwordHash: hashPassword("correctpass123") });
    const resWrongPassword = await POST(jsonRequest({ email: "real@example.com", password: "wrongpass123" }));
    expect(resWrongPassword.status).toBe(401);
    const bodyWrongPassword = await resWrongPassword.json();

    expect(bodyUnknown.error).toBe(bodyWrongPassword.error);
  });

  it("succeeds with the correct password and establishes a session", async () => {
    createUser({ email: "good@example.com", passwordHash: hashPassword("correctpass123") });
    const res = await POST(jsonRequest({ email: "good@example.com", password: "correctpass123" }));
    expect(res.status).toBe(200);
    expect((await getCurrentUser())?.email).toBe("good@example.com");
  });

  it("bootstraps the configured admin email on first successful login, and reflects the promotion in the response", async () => {
    createUser({ email: BOOTSTRAP_EMAIL, passwordHash: hashPassword("adminpass123") });
    expect(hasAuditAction("admin_bootstrap")).toBe(false);

    const res = await POST(jsonRequest({ email: BOOTSTRAP_EMAIL, password: "adminpass123" }));
    const body = await res.json();
    expect(body.role).toBe("ADMIN");
    expect(hasAuditAction("admin_bootstrap")).toBe(true);
    expect((await getCurrentUser())?.role).toBe("ADMIN");
  });

  it("does not bootstrap admin for a non-matching email", async () => {
    createUser({ email: "notadmin@example.com", passwordHash: hashPassword("pass12345") });
    const res = await POST(jsonRequest({ email: "notadmin@example.com", password: "pass12345" }));
    const body = await res.json();
    expect(body.role).toBe("MEMBER");
    expect(hasAuditAction("admin_bootstrap")).toBe(false);
  });

  it("a disabled account cannot log in even with the correct password", async () => {
    const { setUserDisabled } = await import("@/lib/db/users");
    const user = createUser({ email: "disabled@example.com", passwordHash: hashPassword("pass12345") });
    setUserDisabled(user.id, true);
    const res = await POST(jsonRequest({ email: "disabled@example.com", password: "pass12345" }));
    expect(res.status).toBe(401);
  });

  it("400s on a malformed JSON body", async () => {
    const res = await POST(new Request("http://localhost/api/auth/login", { method: "POST", body: "not json" }));
    expect(res.status).toBe(400);
  });
});
