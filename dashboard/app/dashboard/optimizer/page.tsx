import { OptimizerView } from "@/components/OptimizerView";
import { OptimizerWorkspace } from "@/components/optimizer/OptimizerWorkspace";
import { getCurrentUser } from "@/lib/auth/session";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { userCanSelectBigMoneyMlOptimizerSource, userCanSelectBlueCollarOptimizerSource } from "@/lib/entitlements/featureVisibility";
import { listLineupSets } from "@/lib/loaders";
import { userCanUseCanonicalServing } from "@/lib/servingBackend/config";
import { isValidSlateDateString } from "@/lib/slateDate";
import type { LineupSet } from "@/lib/types";

export const dynamic = "force-dynamic";

/** Milestone 14: the interactive lineup builder is the primary
 * experience here -- pick a slate, browse/lock/exclude/set exposure,
 * configure stacking/objective, click Build, inspect results. Every
 * past run saved today (including ones built through this same
 * workspace, since every Build persists an immutable lineup set exactly
 * like the CLI always has) remains browsable below for reference.
 * Milestone 31.2C: an explicit ?date= param (e.g. linked from
 * /admin/slates when DraftKings' live lobby has rolled to the next
 * calendar day ahead of Chicago-today) seeds OptimizerWorkspace's own
 * date selector; "Past Runs" below always stays scoped to Chicago-today
 * specifically, since past lineup builds are inherently a same-day
 * concept, not per-selected-date. */
export default async function OptimizerPage(props: PageProps<"/dashboard/optimizer">) {
  const searchParams = await props.searchParams;
  const dateParam = typeof searchParams.date === "string" ? searchParams.date : undefined;
  // null (not today's date) when no explicit, valid ?date= was given --
  // OptimizerWorkspace then falls through to its own priority order
  // (persisted selection, then the server's own today-default), exactly
  // preserving pre-M31.2C behavior for a bare /dashboard/optimizer visit.
  const initialDate = isValidSlateDateString(dateParam) ? dateParam : null;

  const today = getTodayChicagoDate();
  const loaded = await listLineupSets(today);
  const runs = loaded
    .filter((r): r is typeof r & { data: LineupSet } => r.data !== null)
    .map((r) => ({ filename: r.filename, data: r.data }));

  // Milestone 32.4: Big Money ML optimizer selection is ADMIN/OWNER-only
  // (default ADMIN_ONLY feature flag) -- resolved server-side and passed
  // down as a plain boolean prop; the client component never touches
  // the DB/session itself (see app/api/optimizer/build/route.ts for the
  // matching server-side enforcement -- this prop only controls whether
  // the option is OFFERED in the UI, never the actual authorization).
  const user = await getCurrentUser();
  const canUseBigMoneyMl = await userCanSelectBigMoneyMlOptimizerSource(user);
  // BlueCollar Live Projection Integration: same ADMIN/OWNER-only
  // server-side gate ('mlb.bluecollar_optimizer', default ADMIN_ONLY).
  const canUseBlueCollar = await userCanSelectBlueCollarOptimizerSource(user);
  // T1B/T1C: same pattern, gated by the EXISTING 'mlb.canonical_postgres_serving'
  // ADMIN_ONLY flag (built in M5, never wired into any UI until now).
  // This prop only controls whether the toggle is OFFERED; the three
  // /api/optimizer/* routes already re-authorize every request
  // server-side via resolveServingBackend() regardless of what a client
  // sends.
  const canUseCanonicalServing = await userCanUseCanonicalServing(user);

  return (
    <div>
      <h1 className="mb-1 text-lg font-semibold text-text">Optimizer</h1>
      <p className="mb-4 text-xs text-text-faint">Select a DFS slate date, configure constraints, and build lineups.</p>

      <OptimizerWorkspace
        initialDate={initialDate}
        canUseBigMoneyMl={canUseBigMoneyMl}
        canUseBlueCollar={canUseBlueCollar}
        canUseCanonicalServing={canUseCanonicalServing}
      />

      {runs.length > 0 && (
        <div className="mt-8">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Past Runs Today</h2>
          <OptimizerView runs={runs} />
        </div>
      )}
    </div>
  );
}
