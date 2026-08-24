import { NextResponse } from "next/server";

import { isValidEmail, normalizeEmail } from "@/lib/auth/validators";
import { createPasswordResetToken } from "@/lib/db/tokens";
import { findUserByEmail } from "@/lib/db/users";
import { getEmailAdapter } from "@/lib/email";

export const dynamic = "force-dynamic";

/** Always responds `{ok:true}` with the same generic message regardless
 * of whether the email matches an account -- never reveals which
 * accounts exist through response text. `devResetLink` is present ONLY
 * when a matching account exists; this is a deliberate, DEV-ONLY
 * concession (there is no real email provider to deliver the link
 * out-of-band, so a real reset flow couldn't be tested at all without
 * it) and disappears the moment a real EmailAdapter replaces the dev
 * one -- a production build would never return this field. */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }

  const { email } = (body ?? {}) as { email?: unknown };
  if (typeof email !== "string" || !isValidEmail(email)) {
    return NextResponse.json({ error: "A valid email is required." }, { status: 400 });
  }

  const user = await findUserByEmail(normalizeEmail(email));
  if (!user) {
    return NextResponse.json({ ok: true, message: "If an account exists for that email, a reset link has been sent." });
  }

  const { rawToken } = await createPasswordResetToken(user.id);
  const origin = new URL(request.url).origin;
  const resetLink = `${origin}/reset-password?token=${rawToken}`;
  const { devLink } = await getEmailAdapter().sendPasswordResetEmail({ to: user.email, link: resetLink });

  return NextResponse.json({
    ok: true,
    message: "If an account exists for that email, a reset link has been sent.",
    devResetLink: devLink,
  });
}
