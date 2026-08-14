import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/Header";

export const dynamic = "force-dynamic";

/** Placeholder route for the sidebar's Weather section -- no dedicated
 * weather surface exists yet (today, weather only factors into the
 * Pitcher/Batter Agents' internal environment scoring). Nothing here
 * fabricates a forecast. */
export default function WeatherPage() {
  return (
    <div>
      <PageHeader title="Weather" />
      <EmptyState
        icon="☁"
        title="Weather is not yet available as a dedicated view"
        description="Weather already factors into each game's environment score behind the scenes. A standalone per-game forecast view is planned for a future milestone."
      />
    </div>
  );
}
