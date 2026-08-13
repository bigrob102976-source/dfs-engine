import { NextResponse } from "next/server";

import { validateBuildRequest } from "@/lib/optimizerWorkspace/buildRunner";
import { parseBuildRequest } from "@/lib/optimizerWorkspace/parseBuildRequest";

export const dynamic = "force-dynamic";

/** Fast, authoritative pre-solve validation -- runs the real optimizer's
 * own resolve_settings()/pre_solve_diagnostics() logic (never the CP-SAT
 * solver) so the UI can show "here's what's wrong" before the user
 * clicks Build. See optimizer/constraints.py::pre_solve_diagnostics. */
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

  const errors = await validateBuildRequest(parsed.request);
  return NextResponse.json({ errors });
}
