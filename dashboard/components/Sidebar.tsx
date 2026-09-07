"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

const SPORTS = [
  { code: "MLB", href: "/dashboard", label: "MLB", icon: "⚾" },
  { code: "NFL", href: "/nfl", label: "NFL", icon: "🏈" },
] as const;

const MLB_NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: "🏠" },
  { href: "/dashboard/research", label: "Research", icon: "📊" },
  { href: "/dashboard/environment", label: "Environment", icon: "🌎" },
  { href: "/dashboard/pitchers", label: "Pitchers", icon: "⚾" },
  { href: "/dashboard/hitters", label: "Hitters", icon: "🏏" },
  { href: "/dashboard/stacks", label: "Stacks", icon: "🔥" },
  { href: "/dashboard/weather", label: "Weather", icon: "☁" },
  { href: "/dashboard/vegas", label: "Vegas", icon: "💰" },
  { href: "/dashboard/ownership", label: "Ownership", icon: "🧠" },
  { href: "/dashboard/projections", label: "Projection Lab", icon: "🔬" },
  { href: "/dashboard/slates", label: "Slate Manager", icon: "🗂" },
  { href: "/dashboard/optimizer", label: "Optimizer", icon: "⚙" },
  { href: "/dashboard/portfolio", label: "Portfolio", icon: "📈" },
  { href: "/dashboard/yesterday", label: "Results", icon: "📉" },
  { href: "/dashboard/health", label: "Model Health", icon: "❤" },
];

const NFL_NAV_ITEMS = [
  { href: "/nfl", label: "Dashboard", icon: "🏠" },
  { href: "/nfl/players", label: "Players", icon: "🏃" },
  { href: "/nfl/matchups", label: "Matchups", icon: "🆚" },
  { href: "/nfl/projections", label: "Projections", icon: "🔬" },
  { href: "/nfl/optimizer", label: "Optimizer", icon: "⚙" },
  { href: "/nfl/lineups", label: "Lineups", icon: "📋" },
  { href: "/nfl/saved", label: "Saved / Late Swap", icon: "💾" },
  { href: "/nfl/usage", label: "Usage", icon: "📈" },
];

const STORAGE_KEY = "bigmoney-sidebar-collapsed";

/** Primary navigation for BOTH sports (M16D). Pure presentation -- reads
 * only the URL (usePathname/useSearchParams) and localStorage, makes no
 * auth check and fetches no data, which is exactly what lets the same
 * component render unmodified inside MLB's authenticated
 * app/dashboard/layout.tsx AND NFL's intentionally-public
 * app/nfl/layout.tsx without either one affecting the other's auth
 * behavior. Active sport is derived from the URL (pathname.startsWith
 * ("/nfl")), never from a prop threaded through two differently-gated
 * layouts -- that would risk one sport's server logic leaking into the
 * other's. Collapses to an icon rail (persisted), highlights the active
 * sport AND active page, and always renders the full BIG MONEY DFS
 * wordmark when expanded. */
export function Sidebar() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [collapsed, setCollapsed] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  const activeSport = pathname?.startsWith("/nfl") ? "NFL" : "MLB";
  const navItems = activeSport === "NFL" ? NFL_NAV_ITEMS : MLB_NAV_ITEMS;

  // Milestone 32.6 -- GLOBAL SLATE CONTEXT: every MLB nav link carries the
  // currently-selected ?slate= (and ?date=, when present) forward, so
  // clicking Pitchers/Hitters/Stacks/etc. from the sidebar never drops
  // the user's slate selection back to "Full Day." The GlobalSlateSelector
  // (top nav) is still the only thing that ever WRITES a new slate
  // choice -- this only carries the existing choice across navigation.
  // NFL's equivalent is ?draftGroupId=, carried the same way (mirrors
  // NflSlateSelector's own convention) so switching NFL sidebar pages
  // never drops the selected slate either.
  const slateId = searchParams?.get("slate");
  const dateParam = searchParams?.get("date");
  const draftGroupId = searchParams?.get("draftGroupId");
  const carryParams = new URLSearchParams();
  if (activeSport === "NFL") {
    if (draftGroupId) carryParams.set("draftGroupId", draftGroupId);
  } else {
    if (slateId) carryParams.set("slate", slateId);
    if (dateParam) carryParams.set("date", dateParam);
  }
  const carryQuery = carryParams.toString();

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

      <div className="flex flex-1 flex-col gap-3 overflow-y-auto">
        <div>
          {!collapsed && (
            <div className="mb-1 px-2.5 text-[10px] font-semibold uppercase tracking-widest text-text-faint">Sports</div>
          )}
          <div className="flex flex-col gap-0.5">
            {SPORTS.map((sport) => {
              const active = sport.code === activeSport;
              return (
                <Link
                  key={sport.code}
                  href={sport.href}
                  title={collapsed ? sport.label : undefined}
                  aria-current={active ? "page" : undefined}
                  className={`flex items-center gap-2.5 rounded-[var(--radius-control)] px-2.5 py-1.5 text-sm font-semibold transition-colors duration-150 ${
                    active ? "bg-accent-dim text-accent" : "text-text-muted hover:bg-bg-panel-raised hover:text-text"
                  } ${collapsed ? "justify-center" : ""}`}
                >
                  <span aria-hidden="true">{sport.icon}</span>
                  {!collapsed && <span>{sport.label}</span>}
                </Link>
              );
            })}
          </div>
        </div>

        <div className="flex flex-1 flex-col overflow-y-auto">
          {!collapsed && (
            <div className="mb-1 px-2.5 text-[10px] font-semibold uppercase tracking-widest text-text-faint">
              {activeSport} Navigation
            </div>
          )}
          <div className="flex flex-col gap-0.5">
            {navItems.map((item) => {
              const active = item.href === sportHomeHref(activeSport) ? pathname === item.href : pathname?.startsWith(item.href);
              const href = carryQuery ? `${item.href}?${carryQuery}` : item.href;
              return (
                <Link
                  key={item.href}
                  href={href}
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
        </div>
      </div>
    </nav>
  );
}

function sportHomeHref(sport: "MLB" | "NFL"): string {
  return sport === "NFL" ? "/nfl" : "/dashboard";
}
