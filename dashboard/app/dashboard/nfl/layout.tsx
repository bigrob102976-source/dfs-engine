import { redirect } from "next/navigation";

import { isLocalDevAutoLoginEnabled } from "@/lib/auth/localDevGate";
import { getCurrentUser } from "@/lib/auth/session";
import { requireAdmin } from "@/lib/auth/guards";

export const dynamic = "force-dynamic";

/** NFL UI M1 -- internal-only gate for the whole NFL workspace. Reuses
 * the parent /dashboard layout's shell (Sidebar/TopNavigation) as-is --
 * this layout adds ONLY an admin check on top, so a non-admin member
 * hitting /dashboard/nfl/* is redirected to /dashboard, exactly like
 * /admin/* already behaves. Sidebar.tsx's customer-facing NAV_ITEMS is
 * deliberately never touched -- no member ever sees an NFL link.
 *
 * Local dev auto-login (only when isLocalDevAutoLoginEnabled(), i.e.
 * NODE_ENV=development AND LOCAL_DEV_AUTO_LOGIN=true): a Server
 * Component render can't mutate cookies itself, so a session with no
 * cookie yet is bounced through /api/dev/auto-login (a real Route
 * Handler) which establishes a genuine session via the SAME
 * establishSession() every real login uses, then redirects back here.
 * requireAdmin() below is completely unmodified either way -- it just
 * finds a real session already in place on the redirected request. */
export default async function NflLayout({ children }: { children: React.ReactNode }) {
  if (isLocalDevAutoLoginEnabled()) {
    const user = await getCurrentUser();
    if (!user) {
      redirect("/api/dev/auto-login?next=%2Fdashboard%2Fnfl");
    }
  }

  await requireAdmin();
  return <>{children}</>;
}
