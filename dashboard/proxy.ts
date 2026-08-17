import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Milestone 21: cheap, Edge-compatible UX gate -- replaces the old
 * single-shared-password check. This is NOT the security boundary: it
 * only checks whether a session cookie is present at all, so a logged
 * -out visitor gets redirected to /login immediately instead of
 * rendering a protected page shell first.
 *
 * The REAL authorization (is this token valid? has it expired? what is
 * this user's role?) happens server-side, on every request, via
 * lib/auth/guards.ts's requireAuth()/requireAdmin() (Server Components/
 * layouts) and requireAuthApi()/requireAdminApi() (API routes) -- those
 * always do a fresh database lookup and are what actually enforces
 * access. node:sqlite is a Node.js-runtime API and cannot run in this
 * Edge-compatible proxy, which is exactly why the deep check lives
 * downstream instead of here.
 */

const SESSION_COOKIE = "bigmoney_session";

const PUBLIC_PATH_PREFIXES = [
  "/login",
  "/signup",
  "/forgot-password",
  "/reset-password",
  "/verify-email",
  "/api/auth",
  "/_next",
  // Milestone 22: public marketing page, no auth required to view pricing.
  "/pricing",
  // Stripe's webhook POST carries no session cookie at all -- signature
  // verification (lib/billing/stripeClient.ts's stripeWebhooks) is the
  // entire auth story for this one route, done inside the handler itself.
  "/api/billing/stripe/webhook",
];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (PUBLIC_PATH_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
    return NextResponse.next();
  }

  const hasSessionCookie = Boolean(request.cookies.get(SESSION_COOKIE)?.value);
  if (hasSessionCookie) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
