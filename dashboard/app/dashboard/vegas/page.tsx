import Link from "next/link";

import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/Header";

export const dynamic = "force-dynamic";

/** Placeholder route for the sidebar's Vegas section. Per-game odds/totals
 * now has a dedicated home in the Game Environment terminal (Milestone
 * DS2) -- this page just points there instead of duplicating that view. */
export default function VegasPage() {
  return (
    <div>
      <PageHeader title="Vegas" />
      <EmptyState
        icon="💰"
        title="Vegas now lives in Game Environment"
        description="Moneylines, run lines, game totals, team implied totals, and line movement are part of every game's Environment research."
        action={
          <Link
            href="/dashboard/environment"
            className="inline-flex items-center gap-1.5 rounded-[var(--radius-control)] bg-accent px-3.5 py-2 text-xs font-semibold uppercase tracking-wide text-white transition-colors duration-150 hover:bg-accent-hover"
          >
            Open Game Environment
          </Link>
        }
      />
    </div>
  );
}
