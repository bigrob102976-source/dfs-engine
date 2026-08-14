import { parseLastJsonLine } from "./optimizerWorkspace/jsonLine";
import { runPythonScript, tail } from "./orchestrator/pythonRunner";

export interface GameEnvironmentStatus {
  slate_date: string;
  providers: {
    weather: { provider_name: string; is_mock: boolean; source: string };
    vegas: { provider_name: string; is_mock: boolean; source: string };
    umpire: { provider_name: string; is_mock: boolean; source: string };
    bullpen: { provider_name: string; is_mock: boolean; source: string };
  };
  report: {
    exists: boolean;
    generated_at: string | null;
    game_count: number | null;
    engine_version: string | null;
  };
}

/** Shared by the /api/game-environment/status route (polled by the
 * client-side status card) and any server-rendered page that needs the
 * same data -- provider resolution only ever runs in ONE place
 * (Python's research/game_environment/collector.py, via
 * scripts/game_environment_status.py). */
export async function getGameEnvironmentStatus(date: string): Promise<GameEnvironmentStatus | { error: string }> {
  const result = await runPythonScript("scripts/game_environment_status.py", ["--date", date]);
  const doc = parseLastJsonLine(result.stdout);
  if (!doc || result.exitCode !== 0) {
    return { error: `Unexpected game-environment status failure: ${tail(result.stdout + result.stderr, 500)}` };
  }
  return doc as unknown as GameEnvironmentStatus;
}
