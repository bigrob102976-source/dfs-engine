import { redirect } from "next/navigation";

import { isLocalDevAutoLoginEnabled } from "@/lib/auth/localDevGate";
import { getCurrentUser } from "@/lib/auth/session";
import { requireAuth } from "@/lib/auth/guards";

export const dynamic = "force-dynamic";

/** NFL production access fix -- any authenticated member may use the
 * NFL workspace, matching MLB's own customer-facing pages (requireAuth,
 * not requireAdmin -- see app/dashboard/layout.tsx). This layout nests
 * inside that shared requireAuth()-gated /dashboard layout, so this
 * call is technically redundant but kept explicit: it documents the
 * intended NFL access rule at the exact place a future admin-only
 * regression would most likely be reintroduced. Admin-only operations
 * (e.g. /admin/*) are unaffected -- this file never touched them.
 *
 * Local dev auto-login (only when isLocalDevAutoLoginEnabled(), i.e.
 * NODE_ENV=development AND LOCAL_DEV_AUTO_LOGIN=true): a Server
 * Component render can't mutate cookies itself, so a session with no
 * cookie yet is bounced through /api/dev/auto-login (a real Route
 * Handler) which establishes a genuine session via the SAME
 * establishSession() every real login uses, then redirects back here.
 * requireAuth() below is completely unmodified either way -- it just
 * finds a real session already in place on the redirected request. */
export default async function NflLayout({ children }: { children: React.ReactNode }) {
  if (isLocalDevAutoLoginEnabled()) {
    const user = await getCurrentUser();
    if (!user) {
      redirect("/api/dev/auto-login?next=%2Fdashboard%2Fnfl");
    }
  }

  await requireAuth();
  return <>{children}</>;
}
