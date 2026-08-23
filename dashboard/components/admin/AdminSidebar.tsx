"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ADMIN_NAV_ITEMS = [
  { href: "/admin", label: "Overview", icon: "📊" },
  { href: "/admin/users", label: "Users", icon: "👤" },
  { href: "/admin/subscriptions", label: "Subscriptions", icon: "💳" },
  { href: "/admin/revenue", label: "Revenue", icon: "💰" },
  { href: "/admin/sports", label: "Sports", icon: "🏆" },
  { href: "/admin/features", label: "Features", icon: "🚩" },
  { href: "/admin/slates", label: "Slates", icon: "📋" },
  { href: "/admin/draftkings-unofficial", label: "DK Dev Data", icon: "🧪" },
  { href: "/admin/performance", label: "Performance", icon: "📈" },
  { href: "/admin/system", label: "System", icon: "🖥" },
  { href: "/admin/audit", label: "Audit Log", icon: "🔍" },
];

/** Deliberately visually distinct from the member Sidebar (red strip,
 * different wordmark treatment, "Exit Admin" escape hatch) so an admin
 * always knows they're in a privileged surface, not the regular
 * dashboard. Never rendered alongside TopNavigation/Sidebar. */
export function AdminSidebar() {
  const pathname = usePathname();

  return (
    <nav aria-label="Admin" className="flex h-full w-56 shrink-0 flex-col border-r border-border bg-bg-panel">
      <div className="border-b border-red/40 bg-red/10 px-3 py-2 text-center text-[11px] font-semibold uppercase tracking-[0.2em] text-red">
        ⚠ Admin Panel
      </div>

      <div className="px-3 py-3">
        <div className="text-sm font-semibold tracking-tight text-text">
          BIG MONEY <span className="text-gold">DFS</span>
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-3">
        {ADMIN_NAV_ITEMS.map((item) => {
          const active = item.href === "/admin" ? pathname === item.href : pathname?.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={`flex items-center gap-2.5 rounded-[var(--radius-control)] px-2.5 py-1.5 text-sm transition-colors duration-150 ${
                active ? "bg-accent-dim text-accent" : "text-text-muted hover:bg-bg-panel-raised hover:text-text"
              }`}
            >
              <span aria-hidden="true">{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </div>

      <div className="border-t border-border p-3">
        <Link
          href="/dashboard"
          className="flex items-center gap-1.5 text-xs text-text-faint transition-colors duration-150 hover:text-text"
        >
          ← Exit Admin
        </Link>
      </div>
    </nav>
  );
}
