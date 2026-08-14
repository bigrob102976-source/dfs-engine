import { parseLastJsonLine } from "./optimizerWorkspace/jsonLine";
import { runPythonScript, tail } from "./orchestrator/pythonRunner";

/** Milestone 19: Mock Mode is OFF by default and must be explicitly
 * enabled -- there is no automatic fallback to mock data anywhere in
 * the app anymore (see dfs/providers/config.py). This module is the
 * dashboard's only way to read/write that toggle; the single source of
 * truth stays in Python (config/runtime_settings.py) so both the
 * dashboard and every Python entry point agree on its state. */

export async function getMockModeEnabled(): Promise<boolean> {
  const result = await runPythonScript("scripts/get_mock_mode.py", []);
  const doc = parseLastJsonLine(result.stdout);
  return Boolean(doc?.enabled);
}

export async function setMockModeEnabled(enabled: boolean): Promise<{ ok: true; enabled: boolean } | { error: string }> {
  const result = await runPythonScript("scripts/set_mock_mode.py", ["--enabled", enabled ? "true" : "false"]);
  const doc = parseLastJsonLine(result.stdout);
  if (!doc || result.exitCode !== 0 || doc.status !== "ok") {
    return { error: `Unexpected failure setting Mock Mode: ${tail(result.stdout + result.stderr, 500)}` };
  }
  return { ok: true, enabled: Boolean(doc.enabled) };
}
