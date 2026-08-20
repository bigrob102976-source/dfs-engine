import { DraftKingsUnofficialExplorer } from "@/components/admin/DraftKingsUnofficialExplorer";
import { PageHeader } from "@/components/ui/Header";

export const dynamic = "force-dynamic";

/** Milestone 31.2 -- admin-only development view of the unofficial
 * DraftKings data provider (draftkings_unofficial/). Purely
 * inspection/debugging; never wired into any member-facing page. See
 * components/admin/DraftKingsUnofficialExplorer.tsx for the actual UI
 * and draftkings_unofficial/README.md for the full architecture. */
export default function AdminDraftKingsUnofficialPage() {
  return (
    <div>
      <PageHeader
        title="DraftKings Development Data"
        description="Inspect the unofficial DraftKings data provider -- sports, slates, games, players, salaries, contests, and roster rules. Development-only, never a production data source."
      />
      <div className="mt-4">
        <DraftKingsUnofficialExplorer />
      </div>
    </div>
  );
}
