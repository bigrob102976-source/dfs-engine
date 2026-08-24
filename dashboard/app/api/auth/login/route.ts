import { NextResponse } from "next/server";

import { maybeBootstrapAdmin } from "@/lib/auth/bootstrap";
import { verifyPassword } from "@/lib/auth/password";
import { establishSession } from "@/lib/auth/session";
import { recordUsageEvent } from "@/lib/db/usageEvents";
import { findUserByEmail } from "@/lib/db/users";

export const dynamic = "force-dynamic";

/** A single generic error message for both "no such account" and "wrong
 * password" -- never reveals which one it was (no user enumeration). */
const INVALID_CREDENTIALS_MESSAGE = "Invalid email or password.";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }

  const { email, password } = (body ?? {}) as { email?: unknown; password?: unknown };
  if (typeof email !== "string" || typeof password !== "string" || !email || !password) {
    return NextResponse.json({ error: INVALID_CREDENTIALS_MESSAGE }, { status: 401 });
  }

  const user = await findUserByEmail(email);
  if (!user || user.disabled_at || !verifyPassword(password, user.password_hash)) {
    return NextResponse.json({ error: INVALID_CREDENTIALS_MESSAGE }, { status: 401 });
  }

  await establishSession(user.id, request.headers.get("user-agent"));
  // Bootstrap check runs AFTER password verification -- a successful
  // login is the proof of account control this milestone requires
  // before ever promoting a role. Server-side only; the client never
  // supplies or influences this decision.
  const bootstrapped = await maybeBootstrapAdmin(user);
  await recordUsageEvent({ userId: user.id, eventType: "login" });

  return NextResponse.json({ ok: true, role: bootstrapped ? "ADMIN" : user.role });
}
