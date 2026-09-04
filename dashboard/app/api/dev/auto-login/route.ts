import { NextRequest, NextResponse } from "next/server";

import { isLocalDevAutoLoginEnabled, maybeAutoLoginLocalDev } from "@/lib/auth/localDevAutoLogin";

export const dynamic = "force-dynamic";

function safeNextPath(raw: string | null): string {
  // Open-redirect guard: only ever a same-origin relative path.
  if (raw && raw.startsWith("/") && !raw.startsWith("//") && !raw.includes("://")) return raw;
  return "/dashboard/nfl";
}

/** Local-dev-only session bootstrap Route Handler (cookies can only be
 * mutated here or in a Server Action -- never in a layout/page render,
 * which is why this exists as its own route rather than living inline
 * in app/dashboard/nfl/layout.tsx). If the two-part gate isn't both
 * true, this behaves as a no-op redirect to /login -- normal auth is
 * required, exactly as if this route didn't exist. */
export async function GET(request: NextRequest) {
  const next = safeNextPath(request.nextUrl.searchParams.get("next"));

  if (!isLocalDevAutoLoginEnabled()) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  await maybeAutoLoginLocalDev();
  return NextResponse.redirect(new URL(next, request.url));
}
