import { runPythonScript, tail } from "./orchestrator/pythonRunner";
import { parseLastJsonLine } from "./optimizerWorkspace/jsonLine";

export interface ExternalProjectionsStatus {
  slate_date: string;
  provider: {
    configured_source: "unconfigured" | "explicit" | "unknown";
    reason: string | null;
    provider_key: string | null;
    provider_name: string | null;
    provider_version: string | null;
    is_mock: boolean | null;
    is_configured: boolean;
    available_providers: string[];
  };
  baseline: { exists: boolean; provider_name: string | null; is_mock: boolean | null; retrieved_at: string | null; player_count: number | null };
  adjusted: { exists: boolean; generated_at: string | null; record_count: number | null; adjustment_model_version: string | null };
}

/** Shared by the /api/external-projections/status route (polled by the
 * client-side status card) and the server-rendered Settings page, so
 * the provider-resolution logic only ever runs in ONE place (Python's
 * external_projections/registry.py, via
 * scripts/external_projection_status.py) -- never duplicated in Node.
 * Never returns/logs an API key; the underlying script doesn't read one. */
export async function getExternalProjectionsStatus(date: string): Promise<ExternalProjectionsStatus | { error: string }> {
  const result = await runPythonScript("scripts/external_projection_status.py", ["--date", date]);
  const doc = parseLastJsonLine(result.stdout);
  if (!doc || result.exitCode !== 0) {
    return { error: `Unexpected external-projection status failure: ${tail(result.stdout + result.stderr, 500)}` };
  }
  return doc as unknown as ExternalProjectionsStatus;
}
