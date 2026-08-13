import { NextResponse } from "next/server";

import { buildLineups } from "@/lib/optimizerWorkspace/buildRunner";
import { parseBuildRequest } from "@/lib/optimizerWorkspace/parseBuildRequest";

export const dynamic = "force-dynamic";

/** Builds N lineups against the currently-selected slate's player pool.
 * The only fields accepted are the ones parseBuildRequest validates into
 * a well-typed OptimizerBuildRequest -- nothing here can pass an
 * arbitrary flag, path, or shell content to the Python subprocess (see
 * buildRunner.ts::buildArgv, which only ever emits the fixed set of
 * flags scripts/optimize_dk_lineups.py's own CLI already defines). Every
 * successful build persists an immutable lineup set via the same
 * optimizer/persistence.py every other optimizer run in this project
 * uses. */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }

  const parsed = parseBuildRequest(body);
  if (!parsed.ok) {
    return NextResponse.json({ error: parsed.error }, { status: 400 });
  }

  const result = await buildLineups(parsed.request);
  return NextResponse.json({ result }, { status: result.ok ? 200 : 422 });
}
