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
  // Milestone 33.2.2 hotfix: a load balancer / hosting platform's health
  // check has no session cookie to send -- app/api/health/route.ts's own
  // docstring is this route's real security story (SAFE-only fields,
  // never a credential/path/SQL/stack trace). Exact string, not a
  // shared prefix -- app/api only has this one "health*" route, so this
  // can never accidentally widen to cover a different, actually-
  // protected API route.
  "/api/health",
  // NFL local dev auto-login: this exact route (app/api/dev/auto-login/
  // route.ts) has to be reachable with NO session cookie yet -- that's
  // the whole point of it. Safe to leave public unconditionally: the
  // route's own isLocalDevAutoLoginEnabled() check makes it a no-op
  // redirect to /login whenever NODE_ENV isn't development or the flag
  // isn't set, exactly like every other route it doesn't touch.
  "/api/dev/auto-login",
  // NFL public access: the whole NFL customer product (dashboard,
  // slates, player pool, optimizer, build/generate) is intentionally
  // reachable with no login at all -- see app/nfl/layout.tsx and
  // app/api/nfl/*'s own docstrings for exactly which NFL API routes
  // still require auth (saved lineups / late swap / persisted-lineup
  // export -- all user-owned data, gated by their own requireAuthApi()
  // calls regardless of what this cheap proxy-level check does). This
  // only skips the redirect-to-login; it grants no route anything it
  // doesn't already independently allow.
  "/nfl",
  "/api/nfl",
];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Root path redirects to /nfl (see app/page.tsx) -- must be reachable
  // with no session cookie for that redirect to ever complete for an
  // anonymous visitor. An exact match, never a prefix: "/" would
  // otherwise match every path via startsWith and make everything public.
  if (pathname === "/") {
    return NextResponse.next();
  }

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
