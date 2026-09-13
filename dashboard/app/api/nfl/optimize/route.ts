import { NextResponse } from "next/server";

import { requireAuthApi } from "@/lib/auth/guards";
import { parseLastJsonLine } from "@/lib/optimizerWorkspace/jsonLine";
import { runPythonScript, tail } from "@/lib/orchestrator/pythonRunner";
import { checkRateLimit, getClientIp } from "@/lib/rateLimit";

export const dynamic = "force-dynamic";

// Launch Blocker Sprint 1 (2026-09-13): reversed the prior "NFL public
// access, Phase 6" decision to open this route to anonymous callers.
// This is the most expensive NFL endpoint (a real CP-SAT solve) and is
// exactly the "optimizer execution" case the product decision calls out
// as requiring an account -- matches how /api/optimizer/build (MLB's
// equivalent) has always been gated. The rate limit below is kept as a
// second, independent layer -- authentication alone is not treated as
// sufficient abuse protection for a compute-heavy endpoint, since a
// created account is still a cheap thing to automate.
const OPTIMIZE_RATE_LIMIT_MAX = 20;
const OPTIMIZE_RATE_LIMIT_WINDOW_MS = 5 * 60 * 1000;

interface StackRequestBody {
  qbStackMode?: "off" | "single" | "double";
  bringBackMode?: "off" | "one";
  rbDstEnabled?: boolean;
  maxPlayersPerTeam?: number | null;
  maxPlayersPerGame?: number | null;
}

interface OptimizeRequestBody {
  draftGroupId: number;
  numLineups: number;
  mode?: "roster_feasibility" | "projection" | "ceiling" | "leverage";
  locks?: string[];
  excludes?: string[];
  stack?: StackRequestBody;
  maxExposure?: Record<string, number>;
  maxExposureDefault?: number;
  minExposure?: Record<string, number>;
}

const VALID_MODES = new Set(["roster_feasibility", "projection", "ceiling", "leverage"]);
const VALID_QB_STACK_MODES = new Set(["off", "single", "double"]);
const VALID_BRING_BACK_MODES = new Set(["off", "one"]);

function sanitizeExposureMap(raw: unknown): Record<string, number> {
  if (!raw || typeof raw !== "object") return {};
  const out: Record<string, number> = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof key === "string" && typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1) {
      out[key] = value;
    }
  }
  return out;
}

function sanitizeStack(raw: StackRequestBody | undefined): Record<string, unknown> {
  const qbStackMode = raw?.qbStackMode && VALID_QB_STACK_MODES.has(raw.qbStackMode) ? raw.qbStackMode : "off";
  const bringBackMode = raw?.bringBackMode && VALID_BRING_BACK_MODES.has(raw.bringBackMode) ? raw.bringBackMode : "off";
  const maxPlayersPerTeam = Number.isInteger(raw?.maxPlayersPerTeam) && (raw!.maxPlayersPerTeam as number) > 0 ? raw!.maxPlayersPerTeam : null;
  const maxPlayersPerGame = Number.isInteger(raw?.maxPlayersPerGame) && (raw!.maxPlayersPerGame as number) > 0 ? raw!.maxPlayersPerGame : null;
  return {
    qbStackMode, bringBackMode, rbDstEnabled: raw?.rbDstEnabled === true,
    maxPlayersPerTeam, maxPlayersPerGame,
  };
}

// NFL UI M1/M13 -- runs the REAL nfl/solver.py CP-SAT optimizer (via
// scripts/nfl_dashboard_optimize.py) -- never a reimplementation, never
// a fabricated "feasible" result. Locks/excludes/exposure keys are
// DraftKings player IDs, passed through as opaque strings to the real
// solver, which is itself the only thing that decides feasibility.
// Settings are forwarded as ONE JSON argv element (not many positional
// args) -- see scripts/nfl_dashboard_optimize.py's own docstring for
// the exact contract.
//
// AUTHENTICATED COMPUTE -- an account is required (see the comment on
// OPTIMIZE_RATE_LIMIT_MAX above for why). This route still never reads
// or writes anything scoped to the caller (no user.id used below); the
// account requirement exists purely to raise the cost of automated
// abuse against a real CP-SAT solve, not because the response itself is
// private.
export async function POST(request: Request) {
  const userOrRes = await requireAuthApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  if (!checkRateLimit(`nfl-optimize:${getClientIp(request)}`, OPTIMIZE_RATE_LIMIT_MAX, OPTIMIZE_RATE_LIMIT_WINDOW_MS)) {
    return NextResponse.json({ error: "Too many optimizer requests. Please wait a few minutes and try again." }, { status: 429 });
  }

  let body: OptimizeRequestBody;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Malformed JSON body." }, { status: 400 });
  }

  if (!Number.isInteger(body.draftGroupId) || body.draftGroupId <= 0) {
    return NextResponse.json({ error: "A valid draftGroupId is required." }, { status: 400 });
  }
  const numLineups = Number.isInteger(body.numLineups) && body.numLineups > 0 ? Math.min(body.numLineups, 50) : 1;
  const mode = body.mode && VALID_MODES.has(body.mode) ? body.mode : "roster_feasibility";
  const locks = Array.isArray(body.locks) ? body.locks.filter((v) => typeof v === "string") : [];
  const excludes = Array.isArray(body.excludes) ? body.excludes.filter((v) => typeof v === "string") : [];

  const settings = {
    numLineups, mode, locks, excludes,
    stack: sanitizeStack(body.stack),
    maxExposure: sanitizeExposureMap(body.maxExposure),
    maxExposureDefault: typeof body.maxExposureDefault === "number" && body.maxExposureDefault >= 0 && body.maxExposureDefault <= 1 ? body.maxExposureDefault : 1.0,
    minExposure: sanitizeExposureMap(body.minExposure),
  };

  const args = [String(body.draftGroupId), JSON.stringify(settings)];
  const result = await runPythonScript("scripts/nfl_dashboard_optimize.py", args);
  const parsed = parseLastJsonLine(result.stdout);

  if (result.exitCode !== 0 || !parsed) {
    return NextResponse.json(
      { error: "Failed to run the real NFL optimizer.", details: tail(result.stderr || result.stdout) },
      { status: 502 },
    );
  }
  if (typeof parsed.error === "string") {
    return NextResponse.json({ error: parsed.error, error_type: parsed.error_type ?? null }, { status: 422 });
  }

  return NextResponse.json(parsed);
}
