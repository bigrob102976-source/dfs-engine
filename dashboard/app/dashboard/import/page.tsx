import { ImportCenter } from "@/components/import/ImportCenter";
import { PageHeader } from "@/components/ui/Header";
import { requireAdmin } from "@/lib/auth/guards";
import { getTodayEasternDate } from "@/lib/currentDate";

export const dynamic = "force-dynamic";

/** Milestone 18: Universal Projection Import Center. Reachable from the
 * (admin-only) Settings page's External Data section, or directly at
 * /dashboard/import. Imports any provider's projection CSV as an
 * immutable External Projection baseline snapshot -- the same snapshot
 * format/location a live provider fetch already writes to
 * (external_projections/persistence.py, unchanged), so the Optimizer's
 * External/Adjusted projection sources pick it up with no further
 * wiring. Milestone 29: admin-only -- uploading a third-party data
 * source is a backend data operation, not a member action (its own
 * /api/import/* routes are independently admin-gated too, so this guard
 * is defense-in-depth, not the only enforcement). */
export default async function ImportPage() {
  await requireAdmin();
  const date = getTodayEasternDate();
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
