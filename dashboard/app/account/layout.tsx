import Link from "next/link";

import { requireAuth } from "@/lib/auth/guards";

/** Lightweight account shell -- NOT the full member Sidebar (this is
 * profile/billing self-service, not a DFS research page). */
export default async function AccountLayout({ children }: LayoutProps<"/account">) {
  const user = await requireAuth();

  return (
    <div className="min-h-screen bg-bg">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-bg-panel px-6 py-3">
        <Link href="/dashboard" className="text-sm font-semibold tracking-tight text-text">
          BIG MONEY <span className="text-gold">DFS</span>
        </Link>
        <nav className="flex items-center gap-4 text-xs">
          <Link href="/account" className="text-text-muted hover:text-text">
            Profile
          </Link>
          <Link href="/account/billing" className="text-text-muted hover:text-text">
            Billing
          </Link>
          <span className="text-text-faint">{user.email}</span>
          <form action="/api/auth/logout" method="post">
            <button type="submit" className="text-text-muted hover:text-text">
              Sign out
            </button>
          </form>
        </nav>
      </header>
      <main className="mx-auto max-w-3xl px-6 py-8">{children}</main>
    </div>
  );
}
