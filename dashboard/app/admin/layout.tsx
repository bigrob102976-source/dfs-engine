import { AdminSidebar } from "@/components/admin/AdminSidebar";
import { requireAdmin } from "@/lib/auth/guards";

/** Every /admin/* route is protected here, once, at the layout level --
 * requireAdmin() re-checks the session + role fresh from the DB on
 * every request and redirects non-admins to /dashboard. Renders
 * AdminSidebar instead of the member Sidebar/TopNavigation so admin
 * always looks and feels distinct from the regular member surface. */
export default async function AdminLayout({ children }: LayoutProps<"/admin">) {
  const user = await requireAdmin();

  return (
    <div className="flex h-screen bg-bg">
      <AdminSidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex items-center justify-between border-b border-border bg-bg-panel px-6 py-3">
          <span className="text-xs text-text-faint">Signed in as {user.email}</span>
          <form action="/api/auth/logout" method="post">
            <button type="submit" className="text-xs text-text-muted hover:text-text">
              Sign out
            </button>
          </form>
        </header>
        <main className="flex-1 overflow-y-auto px-6 py-8">{children}</main>
      </div>
    </div>
  );
}
