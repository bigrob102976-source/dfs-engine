import { requireAdmin } from "@/lib/auth/guards";

export const dynamic = "force-dynamic";

/** NFL UI M1 -- internal-only gate for the whole NFL workspace. Reuses
 * the parent /dashboard layout's shell (Sidebar/TopNavigation) as-is --
 * this layout adds ONLY an admin check on top, so a non-admin member
 * hitting /dashboard/nfl/* is redirected to /dashboard, exactly like
 * /admin/* already behaves. Sidebar.tsx's customer-facing NAV_ITEMS is
 * deliberately never touched -- no member ever sees an NFL link. */
export default async function NflLayout({ children }: { children: React.ReactNode }) {
  await requireAdmin();
  return <>{children}</>;
}
