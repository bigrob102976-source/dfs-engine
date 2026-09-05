// MLB AUTOMATIC TOMORROW PREP -- CLI wrapper around
// lib/futureDatePrep.ts::prepareFutureDateIfDue(). Invoked from the SAME
// external worker cycle that already calls
// scripts/refresh-research-and-eligibility.ts for today (see
// worker/run_dk_fetch_worker.ps1, DFS_DEV_AGENT -- not part of this
// repo) -- this is deliberately its OWN separate `railway ssh` round
// trip (not folded into today's own refresh-research-and-eligibility.ts
// call) so a slow/expensive tomorrow-prep run can never compound with
// today's own internal timeout budget; each stage keeps its own
// independent, previously-measured worst-case time budget.
//
// Usage (from dashboard/):
//   npx tsx scripts/prepare-next-day.ts --date 2026-09-04 [--sport MLB] [--throttle-minutes 25]

import { prepareFutureDateIfDue } from "../lib/futureDatePrep.ts";

export function parseArgs(argv: string[]): { date: string; sport: string; throttleMinutes: number } {
  let date: string | undefined;
  let sport = "MLB";
  let throttleMinutes = 25;
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--date") {
      date = argv[i + 1];
      i += 1;
    } else if (argv[i] === "--sport") {
      sport = argv[i + 1];
      i += 1;
    } else if (argv[i] === "--throttle-minutes") {
      throttleMinutes = Number(argv[i + 1]);
      i += 1;
    }
  }
  if (!date) {
    throw new Error("Usage: prepare-next-day.ts --date <YYYY-MM-DD, today's Eastern date> [--sport MLB] [--throttle-minutes 25]");
  }
  return { date, sport, throttleMinutes };
}

async function main() {
  const { date, sport, throttleMinutes } = parseArgs(process.argv.slice(2));
  console.log(`\n===================================================================`);
  console.log(`TOMORROW PREP -- ${sport}, today=${date}`);
  console.log(`===================================================================`);
  const result = await prepareFutureDateIfDue(date, sport, throttleMinutes);
  console.log(JSON.stringify(result, null, 2));
  console.log(`\nRESULT_JSON:${JSON.stringify(result)}`);
}

// Same "always exits 0 on a real business outcome, never on a
// wrapper bug" convention as scripts/refresh-research-and-eligibility.ts
// -- a tomorrow-prep problem must never look like the kind of failure
// that should make the external worker distrust today's own already-
// completed, already-decided result.
main().catch((err) => {
  console.error("UNEXPECTED WRAPPER ERROR:", err);
  console.log(`\nRESULT_JSON:${JSON.stringify({ status: "ERROR", wrapperError: err instanceof Error ? err.message : String(err) })}`);
  process.exitCode = 1;
});
