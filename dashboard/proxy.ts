import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Minimal password gate for this local, read-only dev dashboard -- no
 * user accounts/database, just a single shared password (DASHBOARD_PASSWORD
 * env var) and a signed-ish session cookie. This is the "protected route"
 * mechanism since no pre-existing auth system exists to reuse in this
 * project (see the milestone kickoff discussion).
 *
 * If DASHBOARD_PASSWORD is not set, the gate is disabled entirely (pure
 * localhost convenience during development) -- set it before exposing
 * this beyond your own machine.
 */

const SESSION_COOKIE = "dfs_dashboard_session";

export function proxy(request: NextRequest) {
  const password = process.env.DASHBOARD_PASSWORD;
  if (!password) return NextResponse.next();

  const { pathname } = request.nextUrl;
  if (pathname.startsWith("/login") || pathname.startsWith("/_next") || pathname.startsWith("/api/session")) {
    return NextResponse.next();
  }

  const session = request.cookies.get(SESSION_COOKIE)?.value;
  if (session === password) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
