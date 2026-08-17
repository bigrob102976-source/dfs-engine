import { NextResponse } from "next/server";

import { destroySession } from "@/lib/auth/session";

/** Replaces api/session/sign-out/route.ts. Plain form POST target (the
 * TopNavigation profile menu), not fetch -- a redirect response is what
 * the browser expects here. */
export async function POST(request: Request) {
  await destroySession();
  return NextResponse.redirect(new URL("/login", request.url));
}
