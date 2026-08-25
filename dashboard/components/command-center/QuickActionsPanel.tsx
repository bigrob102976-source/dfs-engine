import Link from "next/link";

import { SectionHeader } from "@/components/ui/Header";

// Optimizer correctness hotfix: only the destinations that are
// themselves slate-scoped (read a `?slate=` param via
// lib/slateContext.ts::resolveSlateContext, or -- for the Optimizer --
// via OptimizerWorkspace.tsx's own identical `?slate=` handling) get the
// currently-selected global slate carried over. Yesterday/History/
// Portfolio have no per-slate concept at all; carrying a param they
// ignore would be harmless but misleading (implies a relationship that
// doesn't exist).
const SLATE_SCOPED_HREFS = new Set(["/dashboard/optimizer", "/dashboard/hitters", "/dashboard/pitchers", "/dashboard/stacks", "/dashboard/ownership", "/dashboard/vegas"]);

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
];

/** RIGHT COLUMN: Quick Actions. Every entry links to an existing
 * member-facing page -- nothing here is a new view. "Weather"
 * deliberately points at /dashboard/environment (where real per-game
 * weather already lives) rather than the /dashboard/weather placeholder,
 * without modifying Weather Intelligence itself. Milestone 29: the
 * "Refresh Research" button and "Import Projections" link (both admin
 * data-source operations now) were removed -- see /admin/slates.
 *
 * Optimizer correctness hotfix: `selectedSlateId` (the SAME global slate
 * selector value app/dashboard/page.tsx already scopes every other
 * section of this page to) is now carried onto every slate-scoped
 * destination as `?slate=`, so "Build Lineups" (and the other slate-
 * scoped quick actions) land on the SAME slate a member is already
 * looking at, instead of silently landing on whatever slate that page's
 * own independent/persisted selection happened to have. */
export function QuickActionsPanel({ selectedSlateId }: { selectedSlateId?: string | null }) {
  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
      <SectionHeader title="Quick Actions" />
      <div className="flex flex-col gap-1.5">
        {LINKS.map((link) => {
          const href = selectedSlateId && SLATE_SCOPED_HREFS.has(link.href) ? `${link.href}?slate=${encodeURIComponent(selectedSlateId)}` : link.href;
          return (
            <Link
              key={link.href}
              href={href}
              className="flex items-center justify-between rounded-[var(--radius-control)] border border-border-subtle bg-bg-panel-raised px-3 py-2 text-xs text-text-muted transition-colors duration-150 hover:border-accent hover:text-text"
            >
              <span>{link.label}</span>
              <span aria-hidden="true" className="text-text-faint">
                →
              </span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
