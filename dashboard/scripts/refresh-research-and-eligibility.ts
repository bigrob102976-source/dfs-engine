// T3/MLB FINISH MODE -- bundles the automatic research/lineup/
// eligibility/projection/ownership side of the pipeline into ONE
// entrypoint that can run from a single `railway ssh` round trip
// (mirroring M4M's own "amortize SSH connection-setup latency across
// one process" fix):
//   1. scripts/build_research_package.py  (MLB schedule/lineups, MLB
//      Stats API -- never DraftKings)
//   2. scripts/refresh_player_identity.py (roster-derived identity
//      crosswalk, MLB Stats API -- never DraftKings)
//   3. lib/db/canonicalEligibility.ts::refreshCanonicalEligibilityForDate
//      (real dfs/eligibility.py computation, Postgres only)
//   4. scripts/run_native_projection_engine.py (real Big Money Native
//      model, date-level, reads research boards -- never DraftKings)
//   5. lib/db/canonicalProjections.ts::refreshCanonicalProjectionsForDate
//      (persists the real Native snapshot onto every real slate, Postgres only)
//   6. lib/db/canonicalOwnership.ts::computeAndPersistOwnershipForSlate,
//      per real slate -- REAL scripts/project_dk_ownership.py against a
//      materialized pool built from steps 3+5's own real output, gated
//      to a slower cadence than 1-5 (see OWNERSHIP_REFRESH_INTERVAL_MINUTES)
//      since it is the most expensive step and does not need to run on
//      every single research-refresh cycle.
//
// This is the EXACT SAME sequence dashboard/lib/slatePipeline.ts's
// runSlatePipeline() already runs for the ADMIN-triggered "Process
// Slate"/"Refresh Data" action -- this script exists ONLY because that
// function is entangled with the DK-dependent legacy pool build (which
// cannot run from inside Railway -- DraftKings blocks Railway's own
// network, confirmed live in M7/M8/T2), so it can never be the thing an
// automatic, Railway-side-triggered cycle calls. Nothing here
// re-implements or diverges from those real functions' own logic; this
// is orchestration only.
//
// Failure isolation (T3 Step 5 / MLB FINISH MODE Phase J): every step is
// independently try/caught. One step failing (e.g. a transient MLB
// Stats API hiccup, or the Native engine having no coverage yet) never
// prevents any OTHER step from running, and never throws out of
// runRefresh() -- this script always exits 0 once it has genuinely
// attempted every step, exactly like refresh_player_identity.py's own
// "always exits 0, reports real status via JSON" convention. It is the
// caller's job (the external worker) to read RESULT_JSON and decide
// whether to alert -- this script itself never blocks or corrupts
// existing CURRENT state on a partial failure (refreshCanonicalEligibilityForDate's
// and refreshCanonicalProjectionsForDate's own per-slate isolation,
// unchanged, still applies underneath steps 3/5).
//
// Usage (from dashboard/):
//   npx tsx scripts/refresh-research-and-eligibility.ts --date 2026-09-02 [--sport MLB]

import { runPythonScript, tail } from "../lib/orchestrator/pythonRunner.ts";
import { refreshCanonicalEligibilityForDate } from "../lib/db/canonicalEligibility.ts";
import { refreshCanonicalProjectionsForDate } from "../lib/db/canonicalProjections.ts";
import { computeAndPersistOwnershipForSlate } from "../lib/db/canonicalOwnership.ts";
import { canonicalGetSlatePool } from "../lib/servingBackend/canonicalPostgresBackend.ts";
import { getExecutor } from "../lib/db/executor.ts";

export function parseArgs(argv: string[]): { date: string; sport: string } {
  let date: string | undefined;
  let sport = "MLB";
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--date") {
      date = argv[i + 1];
      i += 1;
    } else if (argv[i] === "--sport") {
      sport = argv[i + 1];
      i += 1;
    }
  }
  if (!date) {
    throw new Error("Usage: refresh-research-and-eligibility.ts --date <YYYY-MM-DD> [--sport MLB]");
  }
  return { date, sport };
}

interface StepResult {
  ok: boolean;
  detail: string;
}

// MLB FINISH MODE Phase I: ownership is the most expensive step here
// (one real subprocess call PER real slate, each needing a materialized
// pool file) and does not need to run on every research-refresh cycle --
// "recompute when meaningful relevant inputs change" (a fresh projection
// set), not on a fixed short timer. Gated by simply checking how old the
// MOST RECENT real ownership generation already is for this date's
// slates -- no separate state file needed, Postgres is already the
// single source of truth for "when was this last done."
const OWNERSHIP_REFRESH_INTERVAL_MINUTES = 20;

async function runResearchRefresh(date: string): Promise<StepResult> {
  try {
    const result = await runPythonScript("scripts/build_research_package.py", ["--date", date]);
    if (result.exitCode !== 0) return { ok: false, detail: tail(result.stdout + result.stderr, 500) };
    return { ok: true, detail: "OK" };
  } catch (err) {
    return { ok: false, detail: err instanceof Error ? err.message : String(err) };
  }
}

async function runIdentityRefresh(date: string): Promise<StepResult> {
  try {
    const result = await runPythonScript("scripts/refresh_player_identity.py", ["--date", date]);
    if (result.exitCode !== 0) return { ok: false, detail: tail(result.stdout + result.stderr, 500) };
    return { ok: true, detail: "OK" };
  } catch (err) {
    return { ok: false, detail: err instanceof Error ? err.message : String(err) };
  }
}

async function runNativeProjectionEngine(date: string): Promise<StepResult> {
  try {
    const result = await runPythonScript("scripts/run_native_projection_engine.py", ["--date", date]);
    if (result.exitCode !== 0) return { ok: false, detail: tail(result.stdout + result.stderr, 500) };
    return { ok: true, detail: "OK" };
  } catch (err) {
    return { ok: false, detail: err instanceof Error ? err.message : String(err) };
  }
}

interface OwnershipRefreshResult {
  ok: boolean;
  detail: string;
  skipped?: boolean;
  slatesFound?: number;
  slatesUpdated?: number;
  slatesFailed?: number;
}

/** Real ownership generation across every real, currently-VALID
 * canonical slate for `date` -- one slate's failure is caught and
 * reported per-slate, never stopping the others (same pattern every
 * other per-date refresh in this codebase already uses). Only actually
 * runs when due (see OWNERSHIP_REFRESH_INTERVAL_MINUTES); otherwise
 * reports an honest `skipped: true` rather than pretending to have
 * refreshed anything. */
async function refreshOwnershipForDate(date: string, sport: string): Promise<OwnershipRefreshResult> {
  const db = getExecutor();
  const slates = await db.all<{ internal_slate_id: string; provider_slate_id: string }>(
    "SELECT internal_slate_id, provider_slate_id FROM slates WHERE sport = ? AND slate_date = ? AND validation_state = 'VALID'",
    [sport, date],
  );
  if (slates.length === 0) return { ok: true, detail: "No real VALID slates for this date yet.", slatesFound: 0, slatesUpdated: 0, slatesFailed: 0 };

  const mostRecent = await db.get<{ latest: string | null }>(
    `SELECT MAX(generated_at) as latest FROM canonical_slate_player_ownership WHERE internal_slate_id IN (${slates.map(() => "?").join(",")})`,
    slates.map((s) => s.internal_slate_id),
  );
  if (mostRecent?.latest) {
    const ageMinutes = (Date.now() - new Date(mostRecent.latest).getTime()) / 60000;
    if (ageMinutes < OWNERSHIP_REFRESH_INTERVAL_MINUTES) {
      return { ok: true, skipped: true, detail: `Skipped -- most recent ownership generation was ${Math.round(ageMinutes)}m ago (due every ${OWNERSHIP_REFRESH_INTERVAL_MINUTES}m).` };
    }
  }

  let slatesUpdated = 0;
  let slatesFailed = 0;
  for (const slate of slates) {
    try {
      const pool = await canonicalGetSlatePool(date, slate.provider_slate_id, sport);
      const result = await computeAndPersistOwnershipForSlate(slate.internal_slate_id, pool);
      if (result.status === "OK") slatesUpdated += 1;
      else if (result.status !== "NO_USABLE_PLAYERS") slatesFailed += 1; // "no usable players yet" is honest, not a failure
    } catch {
      slatesFailed += 1;
    }
  }

  return { ok: slatesFailed === 0, detail: slatesFailed === 0 ? "OK" : `${slatesFailed}/${slates.length} slate(s) failed`, slatesFound: slates.length, slatesUpdated, slatesFailed };
}

export interface RefreshSummary {
  date: string;
  sport: string;
  research: StepResult;
  identity: StepResult;
  eligibility: { ok: boolean; detail: string; slatesFound?: number; slatesUpdated?: number; slatesFailed?: number };
  nativeProjectionEngine: StepResult;
  projections: { ok: boolean; detail: string; slatesFound?: number; slatesUpdated?: number; slatesFailed?: number };
  ownership: OwnershipRefreshResult;
}

/** The real orchestration logic, exported (and never calling
 * process.exit itself) so it's directly unit-testable -- mirrors how
 * refreshCanonicalEligibilityForDate itself is tested directly rather
 * than only through a CLI wrapper. Never throws: every step is
 * independently try/caught, so a genuinely unexpected exception here
 * would indicate a real bug in this function's own bookkeeping, not a
 * step's failure (those are always captured in the returned summary). */
export async function runRefresh(date: string, sport: string): Promise<RefreshSummary> {
  console.log(`\n===================================================================`);
  console.log(`AUTOMATIC RESEARCH/IDENTITY/ELIGIBILITY/PROJECTION/OWNERSHIP REFRESH -- ${sport} ${date}`);
  console.log(`===================================================================`);

  console.log("\n--- 1/6: research package refresh (MLB Stats API) ---");
  const research = await runResearchRefresh(date);
  console.log(research.ok ? "OK" : `FAILED: ${research.detail}`);

  console.log("\n--- 2/6: player identity crosswalk refresh (MLB Stats API) ---");
  const identity = await runIdentityRefresh(date);
  console.log(identity.ok ? "OK" : `FAILED: ${identity.detail}`);

  console.log("\n--- 3/6: canonical eligibility recompute (Postgres only) ---");
  let eligibility: RefreshSummary["eligibility"];
  try {
    const result = await refreshCanonicalEligibilityForDate(date, sport);
    eligibility = {
      ok: result.slatesFailed === 0,
      detail: result.slatesFailed === 0 ? "OK" : `${result.slatesFailed}/${result.slatesFound} slate(s) failed`,
      slatesFound: result.slatesFound,
      slatesUpdated: result.slatesUpdated,
      slatesFailed: result.slatesFailed,
    };
  } catch (err) {
    eligibility = { ok: false, detail: err instanceof Error ? err.message : String(err) };
  }
  console.log(eligibility.ok ? "OK" : `DEGRADED: ${eligibility.detail}`);

  console.log("\n--- 4/6: Big Money Native projection engine (research boards -- never DraftKings) ---");
  const nativeProjectionEngine = await runNativeProjectionEngine(date);
  console.log(nativeProjectionEngine.ok ? "OK" : `FAILED: ${nativeProjectionEngine.detail}`);

  console.log("\n--- 5/6: canonical projection persistence (Postgres only) ---");
  let projections: RefreshSummary["projections"];
  try {
    const result = await refreshCanonicalProjectionsForDate(date, sport);
    projections = {
      ok: result.slatesFailed === 0,
      detail: result.slatesFailed === 0 ? "OK" : `${result.slatesFailed}/${result.slatesFound} slate(s) failed`,
      slatesFound: result.slatesFound,
      slatesUpdated: result.slatesUpdated,
      slatesFailed: result.slatesFailed,
    };
  } catch (err) {
    projections = { ok: false, detail: err instanceof Error ? err.message : String(err) };
  }
  console.log(projections.ok ? "OK" : `DEGRADED: ${projections.detail}`);

  console.log(`\n--- 6/6: canonical ownership generation (real scripts/project_dk_ownership.py per slate, every ${OWNERSHIP_REFRESH_INTERVAL_MINUTES}m) ---`);
  let ownership: OwnershipRefreshResult;
  try {
    ownership = await refreshOwnershipForDate(date, sport);
  } catch (err) {
    ownership = { ok: false, detail: err instanceof Error ? err.message : String(err) };
  }
  console.log(ownership.skipped ? ownership.detail : ownership.ok ? "OK" : `DEGRADED: ${ownership.detail}`);

  const summary: RefreshSummary = { date, sport, research, identity, eligibility, nativeProjectionEngine, projections, ownership };
  console.log(`\nRESULT_JSON:${JSON.stringify(summary)}`);
  return summary;
}

async function main() {
  const { date, sport } = parseArgs(process.argv.slice(2));
  await runRefresh(date, sport);
}

// Never calls process.exit() explicitly (same convention as this
// project's other scripts/*.ts CLI entrypoints -- see
// promote-canonical-slate.ts) so importing runRefresh()/parseArgs() for
// testing never terminates the importing process; Node's own default
// exit behavior (and this catch handler's process.exitCode) governs the
// real CLI invocation's exit code. Still exits 0 by default (a
// research/projection/ownership-side problem must never look like the
// kind of failure that should make an external caller distrust CURRENT
// canonical slate/salary data, which this script never touches) -- only
// a genuinely unexpected wrapper-level exception (runRefresh() itself is
// designed to never throw; every real step is independently caught
// inside it) sets a non-zero exitCode.
main().catch((err) => {
  console.error("UNEXPECTED WRAPPER ERROR:", err);
  console.log(`\nRESULT_JSON:${JSON.stringify({ ok: false, wrapperError: err instanceof Error ? err.message : String(err) })}`);
  process.exitCode = 1;
});
