"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

const TABS = [
  { href: "/dashboard/nfl", label: "Overview" },
  { href: "/dashboard/nfl/players", label: "Players" },
  { href: "/dashboard/nfl/usage", label: "Usage" },
  { href: "/dashboard/nfl/matchups", label: "Matchups" },
  { href: "/dashboard/nfl/projections", label: "Projections" },
  { href: "/dashboard/nfl/optimizer", label: "Optimizer" },
  { href: "/dashboard/nfl/lineups", label: "Lineups" },
];

/** NFL UI M1 -- the NFL workspace's own tab bar. Lives INSIDE each NFL
 * page's content (not the shared TopNavigation, which stays untouched
 * and MLB-owned) and carries the current ?draftGroupId= forward across
 * every tab, mirroring Sidebar.tsx's existing "?slate=/?date= carried
 * forward" convention for MLB. */
export function NflTabs() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const draftGroupId = searchParams.get("draftGroupId");
  const suffix = draftGroupId ? `?draftGroupId=${draftGroupId}` : "";

  return (
    <nav className="mb-4 flex flex-wrap gap-1 border-b border-border-subtle pb-0" aria-label="NFL workspace">
      {TABS.map((tab) => {
        const active = tab.href === "/dashboard/nfl" ? pathname === tab.href : pathname.startsWith(tab.href);
        return (
          <Link
            key={tab.href}
            href={`${tab.href}${suffix}`}
            className={`rounded-t-[var(--radius-control)] px-3 py-2 text-xs font-semibold uppercase tracking-wide transition-colors ${
              active ? "border-b-2 border-accent text-accent" : "text-text-faint hover:text-text-muted"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
