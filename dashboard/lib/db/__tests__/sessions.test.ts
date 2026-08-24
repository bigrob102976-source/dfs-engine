import { beforeEach, describe, expect, it, vi } from "vitest";

import { __resetDbForTests } from "../client";
import { __resetExecutorForTests } from "../executor";
import { createSession, deleteAllSessionsForUser, deleteSessionByRawToken, findSessionByRawToken } from "../sessions";
import { createUser, setUserDisabled, updateUserRole } from "../users";

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  vi.useRealTimers();
});

describe("sessions", () => {
  it("resolves a valid raw token to its user", async () => {
    const user = await createUser({ email: "session@example.com", passwordHash: "h" });
    const { rawToken } = await createSession(user.id, "test-agent");
    const resolved = await findSessionByRawToken(rawToken);
    expect(resolved?.user.id).toBe(user.id);
  });

  it("returns null for a token that was never issued (forged/tampered cookie)", async () => {
    expect(await findSessionByRawToken("totally-made-up-token")).toBeNull();
  });

  it("returns null and deletes the row once expired", async () => {
    vi.useFakeTimers();
    const user = await createUser({ email: "expiring@example.com", passwordHash: "h" });
    const { rawToken } = await createSession(user.id, null);
    expect(await findSessionByRawToken(rawToken)).not.toBeNull();

    vi.setSystemTime(Date.now() + 31 * 24 * 60 * 60 * 1000); // 31 days later
    expect(await findSessionByRawToken(rawToken)).toBeNull();
    vi.useRealTimers();
  });

  it("role is always read fresh from the DB, never cached on the session/token", async () => {
    const user = await createUser({ email: "rolecheck@example.com", passwordHash: "h" });
    const { rawToken } = await createSession(user.id, null);
    expect((await findSessionByRawToken(rawToken))?.user.role).toBe("MEMBER");

    // Mutate the DB role AFTER the session was created -- the same raw
    // token must reflect the change on the very next lookup, proving
    // authorization is never trusted from anything issued earlier.
    await updateUserRole(user.id, "ADMIN");
    expect((await findSessionByRawToken(rawToken))?.user.role).toBe("ADMIN");
  });

  it("a disabled account's existing sessions stop resolving immediately", async () => {
    const user = await createUser({ email: "disabled@example.com", passwordHash: "h" });
    const { rawToken } = await createSession(user.id, null);
    expect(await findSessionByRawToken(rawToken)).not.toBeNull();

    await setUserDisabled(user.id, true);
    expect(await findSessionByRawToken(rawToken)).toBeNull();
  });

  it("deleteSessionByRawToken invalidates that session only", async () => {
    const user = await createUser({ email: "logout@example.com", passwordHash: "h" });
    const a = await createSession(user.id, null);
    const b = await createSession(user.id, null);
    await deleteSessionByRawToken(a.rawToken);
    expect(await findSessionByRawToken(a.rawToken)).toBeNull();
    expect(await findSessionByRawToken(b.rawToken)).not.toBeNull();
  });

  it("deleteAllSessionsForUser invalidates every session for that user", async () => {
    const user = await createUser({ email: "logoutall@example.com", passwordHash: "h" });
    const a = await createSession(user.id, null);
    const b = await createSession(user.id, null);
    await deleteAllSessionsForUser(user.id);
    expect(await findSessionByRawToken(a.rawToken)).toBeNull();
    expect(await findSessionByRawToken(b.rawToken)).toBeNull();
  });
});
