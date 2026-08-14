import Link from "next/link";

import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/Header";

export const dynamic = "force-dynamic";

/** Placeholder route for the sidebar's Weather section. Per-game weather
 * now has a dedicated home in the Game Environment terminal (Milestone
 * DS2) -- this page just points there instead of duplicating that view. */
export default function WeatherPage() {
  return (
    <div>
      <PageHeader title="Weather" />
      <EmptyState
        icon="☁"
        title="Weather now lives in Game Environment"
        description="Per-game weather (current, first pitch, mid game, late game readings, and deterministic wind/temp/risk conclusions) is part of every game's Environment research."
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
