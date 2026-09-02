// T3 -- bundles the THREE existing, already-tested pieces of the
// research/lineup/eligibility side of the pipeline into ONE entrypoint
// that can run from a single `railway ssh` round trip (mirroring M4M's
// own "amortize SSH connection-setup latency across one process" fix):
//   1. scripts/build_research_package.py  (MLB schedule/lineups, MLB
//      Stats API -- never DraftKings)
//   2. scripts/refresh_player_identity.py (roster-derived identity
//      crosswalk, MLB Stats API -- never DraftKings)
//   3. lib/db/canonicalEligibility.ts::refreshCanonicalEligibilityForDate
//      (real dfs/eligibility.py computation, Postgres only)
//
// This is the EXACT SAME sequence dashboard/lib/slatePipeline.ts's
// runSlatePipeline() already runs for the ADMIN-triggered "Process
// Slate"/"Refresh Data" action -- this script exists ONLY because that
// function is entangled with the DK-dependent legacy pool build (which
// cannot run from inside Railway -- DraftKings blocks Railway's own
// network, confirmed live in M7/M8/T2), so it can never be the thing an
// automatic, Railway-side-triggered cycle calls. Nothing here
// re-implements or diverges from those three functions' own real logic;
// this is orchestration only.
//
// T3 Step 5 failure isolation: each of the three steps is independently
// try/caught. One step failing (e.g. a transient MLB Stats API hiccup)
// never prevents the other two from running, and never throws out of
// main() -- this script always exits 0 once it has genuinely attempted
// all three steps, exactly like refresh_player_identity.py's own "always
// exits 0, reports real status via JSON" convention. It is the caller's
// job (the external worker) to read RESULT_JSON and decide whether to
// alert -- this script itself never blocks or corrupts existing CURRENT
// state on a partial failure (refreshCanonicalEligibilityForDate's own
// per-slate isolation, unchanged, still applies underneath step 3).
//
// Usage (from dashboard/):
//   npx tsx scripts/refresh-research-and-eligibility.ts --date 2026-09-02 [--sport MLB]

import { runPythonScript, tail } from "../lib/orchestrator/pythonRunner.ts";
import { refreshCanonicalEligibilityForDate } from "../lib/db/canonicalEligibility.ts";

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

export interface RefreshSummary {
  date: string;
  sport: string;
  research: StepResult;
  identity: StepResult;
  eligibility: { ok: boolean; detail: string; slatesFound?: number; slatesUpdated?: number; slatesFailed?: number };
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
  console.log(`T3 AUTOMATIC RESEARCH/IDENTITY/ELIGIBILITY REFRESH -- ${sport} ${date}`);
  console.log(`===================================================================`);

  console.log("\n--- 1/3: research package refresh (MLB Stats API) ---");
  const research = await runResearchRefresh(date);
  console.log(research.ok ? "OK" : `FAILED: ${research.detail}`);

  console.log("\n--- 2/3: player identity crosswalk refresh (MLB Stats API) ---");
  const identity = await runIdentityRefresh(date);
  console.log(identity.ok ? "OK" : `FAILED: ${identity.detail}`);

  console.log("\n--- 3/3: canonical eligibility recompute (Postgres only) ---");
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

  const summary: RefreshSummary = { date, sport, research, identity, eligibility };
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
// real CLI invocation's exit code. Still exits 0 by default (T3 Step 5:
// a research-side problem must never look like the kind of failure that
// should make an external caller distrust CURRENT canonical slate/salary
// data, which this script never touches) -- only a genuinely unexpected
// wrapper-level exception (runRefresh() itself is designed to never
// throw; every real step is independently caught inside it) sets a
// non-zero exitCode.
main().catch((err) => {
  console.error("UNEXPECTED WRAPPER ERROR:", err);
  console.log(`\nRESULT_JSON:${JSON.stringify({ ok: false, wrapperError: err instanceof Error ? err.message : String(err) })}`);
  process.exitCode = 1;
});
