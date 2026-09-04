// T3/MLB FINISH MODE -- bundles the automatic research/lineup/
// eligibility/projection/ownership side of the pipeline into ONE
// entrypoint. Extracted from scripts/refresh-research-and-eligibility.ts
// (BREAK-GLASS ADMIN CSV UPLOAD Phase 7) into lib/ so it can be called
// in-process from lib/jobs/slateJobHandlers.ts's REFRESH_CANONICAL_DATE
// job handler -- scripts/*.ts files in this project are CLI entrypoints
// only (each ends with an unconditional `main().catch(...)` at module
// scope, which would fire as an unwanted side effect the instant
// anything imported one), so reusable logic belongs here instead, same
// as lib/slatePipeline.ts already is for the legacy Process/Refresh
// Slate pipeline. scripts/refresh-research-and-eligibility.ts is now a
// thin CLI wrapper around this module's runRefresh() -- pure
// extraction, no behavior change.
//
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
// Slate"/"Refresh Data" action -- this exists ONLY because that
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
// runRefresh().

import { runPythonScript, tail } from "./orchestrator/pythonRunner";
import { refreshCanonicalEligibilityForDate } from "./db/canonicalEligibility";
import { refreshCanonicalProjectionsForDate } from "./db/canonicalProjections";
import { computeAndPersistOwnershipForSlate } from "./db/canonicalOwnership";
import { canonicalGetSlatePool } from "./servingBackend/canonicalPostgresBackend";
import { getExecutor } from "./db/executor";

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

/** MLB FINISH MODE Phase C -- root-caused live in production: the Native
 * projection engine's OWN required input is predictions/<date>/
 * {pitcher,batter}_board_*.json (the Pitcher/Batter Agent's real
 * scoring output, see scripts/run_native_projection_engine.py's own
 * "hard failure if both missing" contract) -- NOT research_output/ or
 * DraftKings. dashboard/lib/slatePipeline.ts's own runSlatePipeline()
 * already re-scores both agents on every refresh (its own M32.7
 * comment), but that function is entangled with the DK-dependent
 * legacy pool build and can never be this automatic path's caller (same
 * reason build_research_package.py/refresh_player_identity.py had to be
 * duplicated here rather than reused via that function). */
async function runPitcherAgent(date: string): Promise<StepResult> {
  try {
    const result = await runPythonScript("scripts/run_real_pitcher_agent.py", ["--date", date]);
    if (result.exitCode !== 0) return { ok: false, detail: tail(result.stdout + result.stderr, 500) };
    return { ok: true, detail: "OK" };
  } catch (err) {
    return { ok: false, detail: err instanceof Error ? err.message : String(err) };
  }
}

async function runBatterAgent(date: string): Promise<StepResult> {
  try {
    const result = await runPythonScript("scripts/run_real_batter_agent.py", ["--date", date]);
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
  failureReasons?: string[];
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
  const failureReasons: string[] = [];
  for (const slate of slates) {
    try {
      const pool = await canonicalGetSlatePool(date, slate.provider_slate_id, sport);
      const result = await computeAndPersistOwnershipForSlate(slate.internal_slate_id, pool);
      if (result.status === "OK") {
        slatesUpdated += 1;
      } else if (result.status !== "NO_USABLE_PLAYERS") {
        slatesFailed += 1;
        failureReasons.push(`${slate.provider_slate_id}: ${result.status}${result.reason ? ` -- ${tail(result.reason, 300)}` : ""}`);
      }
    } catch (err) {
      slatesFailed += 1;
      failureReasons.push(`${slate.provider_slate_id}: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  return {
    ok: slatesFailed === 0,
    detail: slatesFailed === 0 ? "OK" : `${slatesFailed}/${slates.length} slate(s) failed`,
    slatesFound: slates.length, slatesUpdated, slatesFailed,
    failureReasons: failureReasons.length > 0 ? failureReasons : undefined,
  };
}

export interface RefreshSummary {
  date: string;
  sport: string;
  research: StepResult;
  identity: StepResult;
  eligibility: { ok: boolean; detail: string; slatesFound?: number; slatesUpdated?: number; slatesFailed?: number };
  pitcherAgent: StepResult;
  batterAgent: StepResult;
  nativeProjectionEngine: StepResult;
  projections: { ok: boolean; detail: string; slatesFound?: number; slatesUpdated?: number; slatesFailed?: number };
  ownership: OwnershipRefreshResult;
}

/** The real orchestration logic, exported (and never calling
 * process.exit itself) so it's directly unit-testable. Never throws:
 * every step is independently try/caught, so a genuinely unexpected
 * exception here would indicate a real bug in this function's own
 * bookkeeping, not a step's failure (those are always captured in the
 * returned summary). */
export async function runRefresh(date: string, sport: string): Promise<RefreshSummary> {
  console.log(`\n===================================================================`);
  console.log(`AUTOMATIC RESEARCH/IDENTITY/ELIGIBILITY/PROJECTION/OWNERSHIP REFRESH -- ${sport} ${date}`);
  console.log(`===================================================================`);

  console.log("\n--- 1/8: research package refresh (MLB Stats API) ---");
  const research = await runResearchRefresh(date);
  console.log(research.ok ? "OK" : `FAILED: ${research.detail}`);

  console.log("\n--- 2/8: player identity crosswalk refresh (MLB Stats API) ---");
  const identity = await runIdentityRefresh(date);
  console.log(identity.ok ? "OK" : `FAILED: ${identity.detail}`);

  console.log("\n--- 3/8: canonical eligibility recompute (Postgres only) ---");
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

  console.log("\n--- 4/8: pitcher agent scoring (research/Statcast -- never DraftKings) ---");
  const pitcherAgent = await runPitcherAgent(date);
  console.log(pitcherAgent.ok ? "OK" : `FAILED: ${pitcherAgent.detail}`);

  console.log("\n--- 5/8: batter agent scoring (research/Statcast -- never DraftKings) ---");
  const batterAgent = await runBatterAgent(date);
  console.log(batterAgent.ok ? "OK" : `FAILED: ${batterAgent.detail}`);

  console.log("\n--- 6/8: Big Money Native projection engine (pitcher/batter agent boards -- never DraftKings) ---");
  const nativeProjectionEngine = await runNativeProjectionEngine(date);
  console.log(nativeProjectionEngine.ok ? "OK" : `FAILED: ${nativeProjectionEngine.detail}`);

  console.log("\n--- 7/8: canonical projection persistence (Postgres only) ---");
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

  console.log(`\n--- 8/8: canonical ownership generation (real scripts/project_dk_ownership.py per slate, every ${OWNERSHIP_REFRESH_INTERVAL_MINUTES}m) ---`);
  let ownership: OwnershipRefreshResult;
  try {
    ownership = await refreshOwnershipForDate(date, sport);
  } catch (err) {
    ownership = { ok: false, detail: err instanceof Error ? err.message : String(err) };
  }
  console.log(ownership.skipped ? ownership.detail : ownership.ok ? "OK" : `DEGRADED: ${ownership.detail}`);
  if (ownership.failureReasons) {
    for (const reason of ownership.failureReasons) console.log(`  OWNERSHIP FAILURE: ${reason}`);
  }

  const summary: RefreshSummary = { date, sport, research, identity, eligibility, pitcherAgent, batterAgent, nativeProjectionEngine, projections, ownership };
  console.log(`\nRESULT_JSON:${JSON.stringify(summary)}`);
  return summary;
}
