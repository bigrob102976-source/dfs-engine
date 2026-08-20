import { runPythonScript, tail } from "./orchestrator/pythonRunner";
import { parseLastJsonLine } from "./optimizerWorkspace/jsonLine";

export interface FantasyProsStatus {
  slate_date: string;
  slate_id: string | null;
  status: "NOT_CONFIGURED" | "NO_SNAPSHOT" | "AVAILABLE" | "PARTIAL";
  configured: boolean;
  snapshot_exists: boolean;
  retrieved_at: string | null;
  public_api_limited: boolean | null;
  api_tier: string | null;
  hitter_count: number | null;
  pitcher_count: number | null;
  eligible_players: number;
  matched_eligible_players: number;
  unmatched_eligible_names: string[];
}

/** Reads FantasyPros' persisted, observable status (never a live API
 * call) via scripts/fantasypros_status.py -- NOT_CONFIGURED (no API key),
 * NO_SNAPSHOT (configured but nothing fetched yet for this date -- see
 * the admin audit log / recent operations for a live API_ERROR reason
 * from the moment a Process/Refresh actually ran, per
 * lib/slatePipeline.ts), AVAILABLE (covers every optimizer-eligible
 * player in the slate), or PARTIAL (covers only some/zero -- expected
 * given FantasyPros' free-tier sample-only response, see
 * fantasypros/client.py). Never returns/logs an API key. */
export async function getFantasyProsStatus(date: string, slateId: string | null): Promise<FantasyProsStatus | { error: string }> {
  const args = ["--date", date];
  if (slateId) args.push("--slate-id", slateId);
  const result = await runPythonScript("scripts/fantasypros_status.py", args);
  const doc = parseLastJsonLine(result.stdout);
  if (!doc || result.exitCode !== 0) {
    return { error: `Unexpected FantasyPros status failure: ${tail(result.stdout + result.stderr, 500)}` };
  }
  return doc as unknown as FantasyProsStatus;
}
