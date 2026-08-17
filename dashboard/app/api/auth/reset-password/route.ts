import { NextResponse } from "next/server";

import { hashPassword } from "@/lib/auth/password";
import { isValidPassword } from "@/lib/auth/validators";
import { deleteAllSessionsForUser } from "@/lib/db/sessions";
import { consumePasswordResetToken } from "@/lib/db/tokens";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }

  const { token, newPassword } = (body ?? {}) as { token?: unknown; newPassword?: unknown };
  if (typeof token !== "string" || !token) {
    return NextResponse.json({ error: "A reset token is required." }, { status: 400 });
  }
  if (typeof newPassword !== "string" || !isValidPassword(newPassword)) {
    return NextResponse.json({ error: "Password must be at least 8 characters." }, { status: 400 });
  }

  const user = consumePasswordResetToken(token, hashPassword(newPassword));
  if (!user) {
    return NextResponse.json({ error: "This reset link is invalid or has expired." }, { status: 400 });
  }

  // A password reset invalidates every existing session -- anyone who
  // had the old password (or a stolen session) is signed out everywhere.
  deleteAllSessionsForUser(user.id);

  return NextResponse.json({ ok: true });
}
