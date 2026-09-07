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
 * layout or its auth logic. */
export const dynamic = "force-dynamic";

export default function NflLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
