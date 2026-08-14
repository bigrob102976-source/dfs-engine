"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: "🏠" },
  { href: "/dashboard/research", label: "Research", icon: "📊" },
  { href: "/dashboard/pitchers", label: "Pitchers", icon: "⚾" },
  { href: "/dashboard/hitters", label: "Hitters", icon: "🏏" },
  { href: "/dashboard/stacks", label: "Stacks", icon: "🔥" },
  { href: "/dashboard/weather", label: "Weather", icon: "☁" },
  { href: "/dashboard/vegas", label: "Vegas", icon: "💰" },
  { href: "/dashboard/ownership", label: "Ownership", icon: "🧠" },
  { href: "/dashboard/optimizer", label: "Optimizer", icon: "⚙" },
  { href: "/dashboard/portfolio", label: "Portfolio", icon: "📈" },
  { href: "/dashboard/yesterday", label: "Results", icon: "📉" },
  { href: "/dashboard/health", label: "Model Health", icon: "❤" },
  { href: "/dashboard/settings", label: "Settings", icon: "⚙" },
];

const STORAGE_KEY = "bigmoney-sidebar-collapsed";

/** Primary navigation. Collapses to an icon rail (persisted), highlights
 * the active route, and always renders the full BIG MONEY DFS wordmark
 * when expanded -- the one place brand gold appears outside badges. */
export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    Promise.resolve().then(() => {
      try {
        setCollapsed(window.localStorage.getItem(STORAGE_KEY) === "1");
      } catch {
        // Storage unavailable -- default to expanded.
      }
      setHydrated(true);
    });
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
    } catch {
      // Storage unavailable -- collapse state just won't persist across reloads.
    }
  }, [collapsed, hydrated]);

  return (
    <nav
      aria-label="Primary"
      className={`flex h-full shrink-0 flex-col border-r border-border bg-bg-panel p-3 transition-[width] duration-150 ${
        collapsed ? "w-16" : "w-56"
      }`}
    >
      <div className={`mb-4 flex items-center ${collapsed ? "justify-center" : "justify-between px-1"}`}>
        {!collapsed && (
          <div>
            <div className="text-sm font-semibold tracking-tight text-text">
              BIG MONEY <span className="text-gold">DFS</span>
            </div>
            <div className="text-[10px] uppercase tracking-widest text-text-faint">AI Research Terminal</div>
          </div>
        )}
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-pressed={collapsed}
          className="rounded p-1 text-text-faint transition-colors duration-150 hover:bg-bg-panel-raised hover:text-text"
        >
          {collapsed ? "»" : "«"}
        </button>
      </div>

      <div className="flex flex-1 flex-col gap-0.5 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const active = item.href === "/dashboard" ? pathname === item.href : pathname?.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              aria-current={active ? "page" : undefined}
              className={`flex items-center gap-2.5 rounded-[var(--radius-control)] px-2.5 py-1.5 text-sm transition-colors duration-150 ${
                active ? "bg-accent-dim text-accent" : "text-text-muted hover:bg-bg-panel-raised hover:text-text"
              } ${collapsed ? "justify-center" : ""}`}
            >
              <span aria-hidden="true">{item.icon}</span>
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
