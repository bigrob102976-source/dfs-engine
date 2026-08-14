import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/Header";

export const dynamic = "force-dynamic";

/** Placeholder route for the sidebar's Portfolio section -- multi-
 * contest, multi-slate entry tracking doesn't exist yet (today, each
 * optimizer build produces one immutable lineup set, viewable on the
 * Optimizer page). Nothing here fabricates entries or bankroll data. */
export default function PortfolioPage() {
  return (
    <div>
      <PageHeader title="Portfolio" />
      <EmptyState
        icon="📈"
        title="Portfolio tracking is not yet available"
        description="Cross-slate entry and bankroll tracking is planned for a future milestone. Today's lineups are viewable on the Optimizer page."
      />
    </div>
  );
}
