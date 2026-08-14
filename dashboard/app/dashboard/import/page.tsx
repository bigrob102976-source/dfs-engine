import { ImportCenter } from "@/components/import/ImportCenter";
import { PageHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";

export const dynamic = "force-dynamic";

/** Milestone 18: Universal Projection Import Center. Reachable from
 * Settings -> External Data, or directly at /dashboard/import. Imports
 * any provider's projection CSV as an immutable External Projection
 * baseline snapshot -- the same snapshot format/location a live provider
 * fetch already writes to (external_projections/persistence.py,
 * unchanged), so the Optimizer's External/Adjusted projection sources
 * pick it up with no further wiring. */
export default function ImportPage() {
  const date = getTodayChicagoDate();
  return (
    <div>
      <PageHeader
        title="Import Projections"
        description="Upload a projection CSV from any provider. It becomes an immutable snapshot the Optimizer can use as an External or Adjusted projection source."
      />
      <ImportCenter date={date} />
    </div>
  );
}
