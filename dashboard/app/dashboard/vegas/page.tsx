import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/Header";

export const dynamic = "force-dynamic";

/** Placeholder route for the sidebar's Vegas section -- no dedicated
 * odds/totals surface exists yet. Nothing here fabricates lines. */
export default function VegasPage() {
  return (
    <div>
      <PageHeader title="Vegas" />
      <EmptyState
        icon="💰"
        title="Vegas lines are not yet available as a dedicated view"
        description="Team implied totals already factor into the Game Environment research behind the scenes. A standalone odds/totals view is planned for a future milestone."
      />
    </div>
  );
}
