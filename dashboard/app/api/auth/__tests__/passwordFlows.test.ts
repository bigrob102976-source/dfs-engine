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
const { hashPassword, verifyPassword } = await import("@/lib/auth/password");
const { createUser, findUserById } = await import("@/lib/db/users");
const { createEmailVerificationToken } = await import("@/lib/db/tokens");
const { createSession, findSessionByRawToken } = await import("@/lib/db/sessions");
const { establishSession, getCurrentUser } = await import("@/lib/auth/session");
const { POST: verifyEmail } = await import("../verify-email/route");
const { POST: forgotPassword } = await import("../forgot-password/route");
const { POST: resetPassword } = await import("../reset-password/route");
const { POST: logout } = await import("../logout/route");

function jsonRequest(url: string, body: unknown) {
  return new Request(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
});

describe("POST /api/auth/verify-email", () => {
  it("marks the account verified for a valid token", async () => {
    const user = await createUser({ email: "verify@example.com", passwordHash: "h" });
    const { rawToken } = await createEmailVerificationToken(user.id);
    const res = await verifyEmail(jsonRequest("http://localhost/api/auth/verify-email", { token: rawToken }));
    expect(res.status).toBe(200);
    expect((await findUserById(user.id))!.email_verified_at).not.toBeNull();
  });

  it("400s for an unknown token", async () => {
    const res = await verifyEmail(jsonRequest("http://localhost/api/auth/verify-email", { token: "bogus" }));
    expect(res.status).toBe(400);
  });

  it("400s when the same token is used twice", async () => {
    const user = await createUser({ email: "reuse@example.com", passwordHash: "h" });
    const { rawToken } = await createEmailVerificationToken(user.id);
    await verifyEmail(jsonRequest("http://localhost/api/auth/verify-email", { token: rawToken }));
    const second = await verifyEmail(jsonRequest("http://localhost/api/auth/verify-email", { token: rawToken }));
    expect(second.status).toBe(400);
  });
});

describe("POST /api/auth/forgot-password", () => {
  it("returns ok:true with a devResetLink for a real account", async () => {
    await createUser({ email: "forgot@example.com", passwordHash: "h" });
    const res = await forgotPassword(jsonRequest("http://localhost/api/auth/forgot-password", { email: "forgot@example.com" }));
    const body = await res.json();
    expect(body.ok).toBe(true);
    expect(body.devResetLink).toContain("/reset-password?token=");
  });

  it("returns the SAME generic ok:true message for an unknown email (no enumeration in copy)", async () => {
    await createUser({ email: "known@example.com", passwordHash: "h" });
    const known = await (await forgotPassword(jsonRequest("http://localhost/api/auth/forgot-password", { email: "known@example.com" }))).json();
    const unknown = await (await forgotPassword(jsonRequest("http://localhost/api/auth/forgot-password", { email: "unknown@example.com" }))).json();
    expect(known.message).toBe(unknown.message);
    expect(unknown.devResetLink).toBeUndefined();
  });
});

describe("POST /api/auth/reset-password", () => {
  it("sets a new password that then verifies correctly, and invalidates existing sessions", async () => {
    const user = await createUser({ email: "reset@example.com", passwordHash: hashPassword("oldpassword123") });
    const { rawToken: sessionToken } = await createSession(user.id, null);
    expect(await findSessionByRawToken(sessionToken)).not.toBeNull();

    const { createPasswordResetToken } = await import("@/lib/db/tokens");
    const { rawToken } = await createPasswordResetToken(user.id);
    const res = await resetPassword(jsonRequest("http://localhost/api/auth/reset-password", { token: rawToken, newPassword: "newpassword456" }));
    expect(res.status).toBe(200);

    expect(verifyPassword("newpassword456", (await findUserById(user.id))!.password_hash)).toBe(true);
    expect(await findSessionByRawToken(sessionToken)).toBeNull(); // old session invalidated
  });

  it("400s for an unknown/expired token", async () => {
    const res = await resetPassword(jsonRequest("http://localhost/api/auth/reset-password", { token: "bogus", newPassword: "newpassword456" }));
    expect(res.status).toBe(400);
  });

  it("400s for a too-short new password", async () => {
    const user = await createUser({ email: "shortreset@example.com", passwordHash: "h" });
    const { createPasswordResetToken } = await import("@/lib/db/tokens");
    const { rawToken } = await createPasswordResetToken(user.id);
    const res = await resetPassword(jsonRequest("http://localhost/api/auth/reset-password", { token: rawToken, newPassword: "short" }));
    expect(res.status).toBe(400);
  });
});

describe("POST /api/auth/logout", () => {
  it("clears the session and redirects to /login", async () => {
    const user = await createUser({ email: "logout@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    expect(await getCurrentUser()).not.toBeNull();

    const res = await logout(new Request("http://localhost/api/auth/logout", { method: "POST" }));
    expect(res.status).toBe(307); // NextResponse.redirect default
    expect(res.headers.get("location")).toContain("/login");
    expect(await getCurrentUser()).toBeNull();
  });
});
