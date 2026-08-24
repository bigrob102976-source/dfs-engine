import { NextResponse } from "next/server";

import { hashPassword } from "@/lib/auth/password";
import { establishSession } from "@/lib/auth/session";
import { isValidEmail, isValidPassword, normalizeEmail } from "@/lib/auth/validators";
import { createEmailVerificationToken } from "@/lib/db/tokens";
import { recordUsageEvent } from "@/lib/db/usageEvents";
import { createUser, findUserByEmail } from "@/lib/db/users";
import { getEmailAdapter } from "@/lib/email";

export const dynamic = "force-dynamic";

/** Creates the account, signs the user in immediately (email
 * verification is tracked but does not block product access this
 * milestone -- there is no real SMTP provider to depend on for a hard
 * gate), and issues a verification token via the DEV email adapter.
 * `devVerificationLink` is only ever present because no real email
 * provider exists yet -- this is not something a production build with
 * a real EmailAdapter would return. */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }

  const { email, password, displayName } = (body ?? {}) as { email?: unknown; password?: unknown; displayName?: unknown };
  if (typeof email !== "string" || !isValidEmail(email)) {
    return NextResponse.json({ error: "A valid email is required." }, { status: 400 });
  }
  if (typeof password !== "string" || !isValidPassword(password)) {
    return NextResponse.json({ error: "Password must be at least 8 characters." }, { status: 400 });
  }
  if (displayName !== undefined && typeof displayName !== "string") {
    return NextResponse.json({ error: "`displayName` must be a string." }, { status: 400 });
  }

  const normalizedEmail = normalizeEmail(email);
  if (await findUserByEmail(normalizedEmail)) {
    return NextResponse.json({ error: "An account with this email already exists." }, { status: 409 });
  }

  const user = await createUser({
    email: normalizedEmail,
    passwordHash: hashPassword(password),
    displayName: displayName ? displayName.trim() || null : null,
  });

  const { rawToken } = await createEmailVerificationToken(user.id);
  const origin = new URL(request.url).origin;
  const verificationLink = `${origin}/verify-email?token=${rawToken}`;
  const { devLink } = await getEmailAdapter().sendVerificationEmail({ to: user.email, link: verificationLink });

  await establishSession(user.id, request.headers.get("user-agent"));
  await recordUsageEvent({ userId: user.id, eventType: "signup" });

  return NextResponse.json({ ok: true, devVerificationLink: devLink });
}
