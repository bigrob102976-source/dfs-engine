import { getTodayChicagoDate } from "../currentDate";
import { isValidSlateId } from "./validateSlateId";
import type { OptimizerBuildRequest } from "./types";

const OBJECTIVES = new Set(["projection", "ceiling", "balanced", "leverage"]);

export type ParseResult = { ok: true; request: OptimizerBuildRequest } | { ok: false; error: string };

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((v) => typeof v === "string");
}

/** Validates an untrusted JSON request body into a well-typed
 * OptimizerBuildRequest -- the ONLY fields this ever produces are the
 * ones scripts/optimize_dk_lineups.py's own CLI already accepts (see
 * lib/optimizerWorkspace/buildRunner.ts::buildArgv); nothing here can
 * smuggle an arbitrary flag, path, or shell content into the Python
 * subprocess. Date is always resolved server-side, never trusted from
 * the client. */
export function parseBuildRequest(body: unknown): ParseResult {
  if (typeof body !== "object" || body === null) {
    return { ok: false, error: "Request body must be a JSON object." };
  }
  const b = body as Record<string, unknown>;

  if (!isValidSlateId(b.slateId)) {
    return { ok: false, error: "\"slateId\" (string) is required." };
  }

  const lineups = Number(b.lineups);
  if (!Number.isInteger(lineups) || lineups < 1 || lineups > 150) {
    return { ok: false, error: "\"lineups\" must be an integer between 1 and 150." };
  }

  const objective = typeof b.objective === "string" ? b.objective : "projection";
  if (!OBJECTIVES.has(objective)) {
    return { ok: false, error: `"objective" must be one of ${[...OBJECTIVES].join(", ")}.` };
  }

  const locks = b.locks === undefined ? [] : b.locks;
  if (!isStringArray(locks)) return { ok: false, error: "\"locks\" must be an array of player names." };

  const exclusions = b.exclusions === undefined ? [] : b.exclusions;
  if (!isStringArray(exclusions)) return { ok: false, error: "\"exclusions\" must be an array of player names." };

  const maxExposureRaw = b.maxExposure === undefined ? {} : b.maxExposure;
  if (typeof maxExposureRaw !== "object" || maxExposureRaw === null || Array.isArray(maxExposureRaw)) {
    return { ok: false, error: "\"maxExposure\" must be an object of player name -> fraction." };
  }
  const maxExposure: Record<string, number> = {};
  for (const [name, value] of Object.entries(maxExposureRaw as Record<string, unknown>)) {
    const fraction = Number(value);
    if (!Number.isFinite(fraction) || fraction < 0 || fraction > 1) {
      return { ok: false, error: `"maxExposure" fraction for "${name}" must be between 0 and 1.` };
    }
    maxExposure[name] = fraction;
  }

  const stackSize = b.stackSize === undefined || b.stackSize === null ? null : Number(b.stackSize);
  if (stackSize !== null && (!Number.isInteger(stackSize) || stackSize < 2 || stackSize > 5)) {
    return { ok: false, error: "\"stackSize\" must be an integer between 2 and 5, or null." };
  }

  const stackTeam = b.stackTeam === undefined || b.stackTeam === null ? null : String(b.stackTeam);

  const minSalary = b.minSalary === undefined || b.minSalary === null ? null : Number(b.minSalary);
  if (minSalary !== null && (!Number.isFinite(minSalary) || minSalary < 0)) {
    return { ok: false, error: "\"minSalary\" must be a non-negative number, or null." };
  }

  const minUnique = b.minUnique === undefined ? 2 : Number(b.minUnique);
  if (!Number.isInteger(minUnique) || minUnique < 1 || minUnique > 4) {
    return { ok: false, error: "\"minUnique\" must be an integer between 1 and 4." };
  }

  const minConfidence = b.minConfidence === undefined || b.minConfidence === null ? null : Number(b.minConfidence);
  if (minConfidence !== null && !Number.isFinite(minConfidence)) {
    return { ok: false, error: "\"minConfidence\" must be a number, or null." };
  }

  const maxPlayerRisk = b.maxPlayerRisk === undefined || b.maxPlayerRisk === null ? null : Number(b.maxPlayerRisk);
  if (maxPlayerRisk !== null && !Number.isFinite(maxPlayerRisk)) {
    return { ok: false, error: "\"maxPlayerRisk\" must be a number, or null." };
  }

  return {
    ok: true,
    request: {
      date: getTodayChicagoDate(),
      slateId: b.slateId,
      lineups,
      objective: objective as OptimizerBuildRequest["objective"],
      locks,
      exclusions,
      maxExposure,
      stackSize,
      stackTeam,
      allowPitcherVsHitter: Boolean(b.allowPitcherVsHitter),
      minSalary,
      minUnique,
      minConfidence,
      maxPlayerRisk,
    },
  };
}
