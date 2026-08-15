import Link from "next/link";

import { RefreshResearchButton } from "./RefreshResearchButton";
import { SectionHeader } from "@/components/ui/Header";

const LINKS: Array<{ label: string; href: string }> = [
  { label: "Build Lineups", href: "/dashboard/optimizer" },
  { label: "Top Hitters", href: "/dashboard/hitters" },
  { label: "Top Pitchers", href: "/dashboard/pitchers" },
  { label: "Stacks", href: "/dashboard/stacks" },
  { label: "Ownership", href: "/dashboard/ownership" },
  { label: "Weather", href: "/dashboard/environment" },
  { label: "Vegas", href: "/dashboard/vegas" },
  { label: "Yesterday", href: "/dashboard/yesterday" },
  { label: "History", href: "/dashboard/history" },
  { label: "Portfolio", href: "/dashboard/portfolio" },
  { label: "Import Projections", href: "/dashboard/import" },
];

/** RIGHT COLUMN: Quick Actions. Every entry links to an existing page --
 * nothing here is a new view. "Weather" deliberately points at
 * /dashboard/environment (where real per-game weather already lives)
 * rather than the /dashboard/weather placeholder, without modifying
 * Weather Intelligence itself. */
export function QuickActionsPanel() {
  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
      <SectionHeader title="Quick Actions" />
      <div className="flex flex-col gap-1.5">
        {LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className="flex items-center justify-between rounded-[var(--radius-control)] border border-border-subtle bg-bg-panel-raised px-3 py-2 text-xs text-text-muted transition-colors duration-150 hover:border-accent hover:text-text"
          >
            <span>{link.label}</span>
            <span aria-hidden="true" className="text-text-faint">
              →
            </span>
          </Link>
        ))}
        <RefreshResearchButton />
      </div>
    </div>
  );
}
