import { beforeEach, describe, expect, it, vi } from "vitest";

import { __resetDbForTests } from "../client";
import { createSession, deleteAllSessionsForUser, deleteSessionByRawToken, findSessionByRawToken } from "../sessions";
import { createUser, setUserDisabled, updateUserRole } from "../users";

beforeEach(() => {
  __resetDbForTests();
  vi.useRealTimers();
});

describe("sessions", () => {
  it("resolves a valid raw token to its user", () => {
    const user = createUser({ email: "session@example.com", passwordHash: "h" });
    const { rawToken } = createSession(user.id, "test-agent");
    const resolved = findSessionByRawToken(rawToken);
    expect(resolved?.user.id).toBe(user.id);
  });

  it("returns null for a token that was never issued (forged/tampered cookie)", () => {
    expect(findSessionByRawToken("totally-made-up-token")).toBeNull();
  });

  it("returns null and deletes the row once expired", () => {
    vi.useFakeTimers();
    const user = createUser({ email: "expiring@example.com", passwordHash: "h" });
    const { rawToken } = createSession(user.id, null);
    expect(findSessionByRawToken(rawToken)).not.toBeNull();

    vi.setSystemTime(Date.now() + 31 * 24 * 60 * 60 * 1000); // 31 days later
    expect(findSessionByRawToken(rawToken)).toBeNull();
    vi.useRealTimers();
  });

  it("role is always read fresh from the DB, never cached on the session/token", () => {
    const user = createUser({ email: "rolecheck@example.com", passwordHash: "h" });
    const { rawToken } = createSession(user.id, null);
    expect(findSessionByRawToken(rawToken)?.user.role).toBe("MEMBER");

    // Mutate the DB role AFTER the session was created -- the same raw
    // token must reflect the change on the very next lookup, proving
    // authorization is never trusted from anything issued earlier.
    updateUserRole(user.id, "ADMIN");
    expect(findSessionByRawToken(rawToken)?.user.role).toBe("ADMIN");
  });

  it("a disabled account's existing sessions stop resolving immediately", () => {
    const user = createUser({ email: "disabled@example.com", passwordHash: "h" });
    const { rawToken } = createSession(user.id, null);
    expect(findSessionByRawToken(rawToken)).not.toBeNull();

    setUserDisabled(user.id, true);
    expect(findSessionByRawToken(rawToken)).toBeNull();
  });

  it("deleteSessionByRawToken invalidates that session only", () => {
    const user = createUser({ email: "logout@example.com", passwordHash: "h" });
    const a = createSession(user.id, null);
    const b = createSession(user.id, null);
    deleteSessionByRawToken(a.rawToken);
    expect(findSessionByRawToken(a.rawToken)).toBeNull();
    expect(findSessionByRawToken(b.rawToken)).not.toBeNull();
  });

  it("deleteAllSessionsForUser invalidates every session for that user", () => {
    const user = createUser({ email: "logoutall@example.com", passwordHash: "h" });
    const a = createSession(user.id, null);
    const b = createSession(user.id, null);
    deleteAllSessionsForUser(user.id);
    expect(findSessionByRawToken(a.rawToken)).toBeNull();
    expect(findSessionByRawToken(b.rawToken)).toBeNull();
  });
});
