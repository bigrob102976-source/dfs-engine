import { NextResponse } from "next/server";

import { parseLastJsonLine } from "@/lib/optimizerWorkspace/jsonLine";
import { runPythonScript, tail } from "@/lib/orchestrator/pythonRunner";
import { checkRateLimit, getClientIp } from "@/lib/rateLimit";

export const dynamic = "force-dynamic";

// PUBLIC READ -- NFL UI M1, real DraftKings NFL Classic slate discovery
// (never hardcoded to one DraftGroup; scripts/nfl_dashboard_slates.py is
// the same real discovery path scripts/nfl_dashboard_data.py itself
// uses). Stays public per the Launch Blocker Sprint 1 product decision
// (public research/slate browsing requires no account); the underlying
// script already prefers a cached snapshot (nfl/pool_cache.py) over a
// live DraftKings call in the common case. Rate-limited below -- Sprint
// 1 found this route had NONE, unlike every other public NFL GET.
const SLATES_RATE_LIMIT_MAX = 30;
const SLATES_RATE_LIMIT_WINDOW_MS = 5 * 60 * 1000;

export async function GET(request: Request) {
  if (!checkRateLimit(`nfl-slates:${getClientIp(request)}`, SLATES_RATE_LIMIT_MAX, SLATES_RATE_LIMIT_WINDOW_MS)) {
    return NextResponse.json({ error: "Too many requests. Please wait a few minutes and try again." }, { status: 429 });
  }

  const result = await runPythonScript("scripts/nfl_dashboard_slates.py", []);
  const parsed = parseLastJsonLine(result.stdout);

  if (result.exitCode !== 0 || !parsed) {
    return NextResponse.json(
      { error: "Failed to discover real NFL slates.", details: tail(result.stderr || result.stdout) },
      { status: 502 },
    );
  }
  if (typeof parsed.error === "string") {
    return NextResponse.json({ error: parsed.error }, { status: 422 });
  }

  return NextResponse.json(parsed);
}
