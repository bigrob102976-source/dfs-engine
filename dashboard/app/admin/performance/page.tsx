import { MlForwardHistoryPanel } from "@/components/admin/MlForwardHistoryPanel";
import { MlForwardResultsPanel } from "@/components/admin/MlForwardResultsPanel";
import { PageHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { listMlForwardResultsDates, listMlForwardResultsSlateIds, loadLatestMlForwardResults } from "@/lib/mlForwardResults";

export const dynamic = "force-dynamic";

/** Milestone 32.5 -- Big Money ML forward RESULTS + LINEUP GRADING.
 * ADMIN-only (gated by app/admin/layout.tsx's requireAdmin()). Grades
 * ML/Native/AI/FantasyPros pregame projections and every saved M32.4
 * lineup set against REAL, postgame MLB results -- never a CSV, never
 * mock/synthetic data. Reads already-persisted immutable documents
 * only; the "Collect Results" action (client component) is what
 * actually triggers a new collection run. */
export default async function AdminPerformancePage(props: PageProps<"/admin/performance">) {
  const searchParams = await props.searchParams;
  const dateParam = typeof searchParams.date === "string" ? searchParams.date : undefined;
  const slateIdParam = typeof searchParams.slateId === "string" ? searchParams.slateId : undefined;

  const knownDates = listMlForwardResultsDates();
  const date = dateParam ?? knownDates[0] ?? getTodayChicagoDate();
  const knownSlateIds = listMlForwardResultsSlateIds(date);
  const slateId = slateIdParam ?? knownSlateIds[0] ?? "";

  const document = slateId ? loadLatestMlForwardResults(date, slateId) : null;

  return (
    <div>
      <PageHeader
        title="Big Money ML Performance"
        description="Grades Big Money ML (and Native/AI/FantasyPros for comparison) against real, completed MLB results. Evaluation only -- never feeds back into any model, the optimizer, or ownership."
      />

      {knownSlateIds.length === 0 && !slateIdParam ? (
        <p className="mb-4 text-xs text-text-faint">
          No slate has been collected yet. Provide a specific slate via <code>?date=YYYY-MM-DD&amp;slateId=dkunofficial-XXXXXX</code> (matching an
          M32.4 optimizer build) and click Collect Results below.
        </p>
      ) : (
        <p className="mb-4 text-xs text-text-faint">
          Slate: {date} / {slateId || "(none selected)"}
        </p>
      )}

      <div className="flex flex-col gap-4">
        <MlForwardResultsPanel date={date} slateId={slateId} document={document} />
        <MlForwardHistoryPanel />
      </div>
    </div>
  );
}
