import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const SESSION_COOKIE = "dfs_dashboard_session";

/** Clears the dashboard session cookie set by app/login/page.tsx and
 * sends the browser back to the login screen. Plain form POST (the
 * TopNavigation profile menu), not fetch -- a redirect response is what
 * the browser expects here. */
export async function POST(request: Request) {
  const store = await cookies();
  store.delete(SESSION_COOKIE);
  return NextResponse.redirect(new URL("/login", request.url));
}
