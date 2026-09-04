// T3/MLB FINISH MODE -- CLI wrapper around lib/canonicalRefresh.ts::runRefresh()
// (research/lineup/eligibility/projection/ownership refresh, date-level).
// The actual orchestration logic lives in lib/ (BREAK-GLASS ADMIN CSV
// UPLOAD Phase 7 extracted it there so lib/jobs/slateJobHandlers.ts's
// REFRESH_CANONICAL_DATE job handler can call runRefresh() in-process --
// see that module's own comment for why importing a scripts/*.ts file
// directly would have been unsafe). This file is now CLI-only: argument
// parsing plus the process entrypoint.
//
// Usage (from dashboard/):
//   npx tsx scripts/refresh-research-and-eligibility.ts --date 2026-09-02 [--sport MLB]

import { runRefresh } from "../lib/canonicalRefresh.ts";

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

export { runRefresh };
export type { RefreshSummary } from "../lib/canonicalRefresh.ts";

async function main() {
  const { date, sport } = parseArgs(process.argv.slice(2));
  await runRefresh(date, sport);
}

// Never calls process.exit() explicitly (same convention as this
// project's other scripts/*.ts CLI entrypoints -- see
// promote-canonical-slate.ts) so importing parseArgs()/runRefresh() for
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
