import { Sidebar } from "@/components/Sidebar";

/** NFL public access -- the NFL customer product (dashboard, slates,
 * player pool, optimizer, lineup building/export) requires NO login at
 * all; this layout never redirects an anonymous visitor. This is a
 * deliberate, separate decision from account-owned features: Saved
 * Lineups / Late Swap / persisted-lineup export still require a real
 * session, enforced independently by their own API routes'
 * requireAuthApi() calls (dashboard/lib/db/nflSavedLineups.ts's
 * ownership checks) regardless of what this layout does -- an
 * anonymous visitor can open those PAGES (no redirect loop), but their
 * data calls 401 and the page itself shows a sign-in prompt rather than
 * bouncing the whole NFL product to /login. Admin-only operations
 * (/admin/*) are unaffected -- this file never touches them.
 *
 * This is intentionally NOT nested under app/dashboard/layout.tsx
 * (which still requireAuth()s every /dashboard/* route for MLB) -- NFL
 * moved to its own top-level /nfl route specifically so this file could
 * make that call independently, with zero changes to MLB's shared
 * layout or its auth logic.
 *
 * M16D -- UNIFIED SHELL: renders the SAME <Sidebar/> MLB's dashboard
 * layout renders, so both sports share one primary navigation system
 * (sport switcher + sport-specific nav) instead of NFL's previous
 * standalone in-page tab bar. This is safe specifically because
 * Sidebar is pure presentation (reads only the URL and localStorage) --
 * it performs no auth check and fetches no data, so embedding it here
 * adds zero auth surface. No TopNavigation (MLB's authenticated header
 * with account/admin menu) is rendered -- NFL has no equivalent
 * concept and doesn't need one; each NFL page's own PageHeader already
 * carries the page title and slate selector. */
export const dynamic = "force-dynamic";

export default function NflLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen w-full overflow-hidden bg-bg">
      <Sidebar />
      <main className="min-w-0 flex-1 overflow-y-auto p-5">{children}</main>
    </div>
  );
}
