import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { parseLastJsonLine } from "@/lib/optimizerWorkspace/jsonLine";
import { runPythonScript, tail } from "@/lib/orchestrator/pythonRunner";

export const dynamic = "force-dynamic";

// NFL UI M1 -- this real data assembly (a full prior-season historical
// fetch + live DK pool build + real model inference) takes ~15-30s.
// A short in-memory cache means switching between NFL tabs for the
// SAME slate doesn't re-run it every navigation -- this is a dev-only,
// single-process cache appropriate for local review, not a production
// caching strategy. `refresh=1` bypasses it explicitly.
const CACHE_TTL_MS = 5 * 60 * 1000;
const cache = new Map<number, { data: Record<string, unknown>; fetchedAt: number }>();

// NFL UI M1 -- internal-only (admin) real NFL slate data endpoint.
// Spawns the real Python data-assembly bridge (scripts/nfl_dashboard_
// data.py) -- never fabricates a value the script itself didn't
// produce. See that script's own module docstring for exactly what
// "real" means for every field.
export async function GET(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const { searchParams } = new URL(request.url);
  const draftGroupIdRaw = searchParams.get("draftGroupId");
  const draftGroupId = draftGroupIdRaw ? Number.parseInt(draftGroupIdRaw, 10) : NaN;
  if (!Number.isInteger(draftGroupId) || draftGroupId <= 0) {
    return NextResponse.json({ error: "A valid draftGroupId query parameter is required." }, { status: 400 });
  }

  const forceRefresh = searchParams.get("refresh") === "1";
  const cached = cache.get(draftGroupId);
  if (!forceRefresh && cached && Date.now() - cached.fetchedAt < CACHE_TTL_MS) {
    return NextResponse.json(cached.data);
  }

  const result = await runPythonScript("scripts/nfl_dashboard_data.py", [String(draftGroupId)]);
  const parsed = parseLastJsonLine(result.stdout);

  if (result.exitCode !== 0 || !parsed) {
    return NextResponse.json(
      { error: "Failed to load real NFL slate data.", details: tail(result.stderr || result.stdout) },
      { status: 502 },
    );
  }
  if (typeof parsed.error === "string") {
    return NextResponse.json({ error: parsed.error }, { status: 422 });
  }

  cache.set(draftGroupId, { data: parsed, fetchedAt: Date.now() });
  return NextResponse.json(parsed);
}
