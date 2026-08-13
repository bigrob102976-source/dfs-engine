import { NextResponse } from "next/server";

import { getCurrentRun, startRefresh, type StartRefreshOptions } from "@/lib/orchestrator/runner";
import type { PipelineStepId } from "@/lib/orchestrator/types";

export const dynamic = "force-dynamic";

const VALID_STEP_IDS: readonly PipelineStepId[] = ["research", "pitchers", "batters", "dfsSalaries", "playerPool", "ownership", "optimizer"];

/** Returns the current (or most recently completed) refresh run, or null
 * if none has ever run in this environment. Polled by the dashboard's
 * RefreshPanel, SlateReadiness, and MissingDataState components while a
 * run is active. */
export async function GET() {
  return NextResponse.json({ run: getCurrentRun() });
}

/** Starts a refresh run. An empty/missing body is the original one-click
 * "Refresh Today's Slate": every step always re-runs, unconditionally.
 * Milestone 16: an optional body `{ "targetSteps": [...], "smart": true }`
 * requests a missing-data-only refresh instead -- only the dependency
 * closure of targetSteps runs, and any step in that closure whose
 * artifact already exists is skipped rather than re-invoked. Every
 * targetSteps value is validated against the fixed, known set of
 * pipeline step ids before it ever reaches the orchestrator -- arbitrary
 * browser input can't smuggle anything else in. The slate date is
 * always resolved server-side, never supplied by the client. Returns
 * 409 if a run is already in progress or paused awaiting a slate
 * selection. */
export async function POST(request: Request) {
  let options: StartRefreshOptions | undefined;

  const rawBody = await request.text();
  if (rawBody.trim()) {
    let body: unknown;
    try {
      body = JSON.parse(rawBody);
    } catch {
      return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
    }
    const targetStepsRaw = (body as { targetSteps?: unknown } | null)?.targetSteps;
    if (targetStepsRaw !== undefined) {
      if (!Array.isArray(targetStepsRaw) || !targetStepsRaw.every((s) => VALID_STEP_IDS.includes(s))) {
        return NextResponse.json({ error: `"targetSteps" must be an array drawn from ${VALID_STEP_IDS.join(", ")}.` }, { status: 400 });
      }
    }
    options = {
      targetSteps: targetStepsRaw as PipelineStepId[] | undefined,
      smart: Boolean((body as { smart?: unknown } | null)?.smart),
    };
  }

  const result = startRefresh(options);
  if (!result.accepted) {
    return NextResponse.json({ run: result.run, error: "A refresh is already in progress." }, { status: 409 });
  }
  return NextResponse.json({ run: result.run }, { status: 202 });
}
