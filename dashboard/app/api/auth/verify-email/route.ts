import { NextResponse } from "next/server";

import { consumeEmailVerificationToken } from "@/lib/db/tokens";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }

  const { token } = (body ?? {}) as { token?: unknown };
  if (typeof token !== "string" || !token) {
    return NextResponse.json({ error: "A verification token is required." }, { status: 400 });
  }

  const user = await consumeEmailVerificationToken(token);
  if (!user) {
    return NextResponse.json({ error: "This verification link is invalid or has expired." }, { status: 400 });
  }

  return NextResponse.json({ ok: true });
}
