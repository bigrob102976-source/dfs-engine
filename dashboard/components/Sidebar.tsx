"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Today's Slate" },
  { href: "/dashboard/pitchers", label: "Top Pitchers" },
  { href: "/dashboard/hitters", label: "Top Hitters" },
  { href: "/dashboard/stacks", label: "Stacks" },
  { href: "/dashboard/optimizer", label: "Optimizer" },
  { href: "/dashboard/yesterday", label: "Yesterday" },
  { href: "/dashboard/history", label: "History" },
  { href: "/dashboard/health", label: "Model Health" },
  { href: "/dashboard/settings", label: "Settings" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <nav className="flex h-full w-52 shrink-0 flex-col gap-0.5 border-r border-border bg-bg-panel p-3">
      <div className="mb-4 px-2">
        <div className="text-sm font-semibold text-text">DFS Command Center</div>
        <div className="text-[11px] text-text-faint">mlb-dfs-engine</div>
      </div>
      {NAV_ITEMS.map((item) => {
        const active = item.href === "/dashboard" ? pathname === item.href : pathname?.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`rounded px-2 py-1.5 text-sm transition-colors ${
              active ? "bg-accent-dim text-text" : "text-text-muted hover:bg-bg-panel-raised hover:text-text"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
