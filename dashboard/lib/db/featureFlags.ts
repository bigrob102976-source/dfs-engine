import { getExecutor } from "./executor";
import type { FeatureFlag, FeatureFlagState } from "./types";

export async function listFeatureFlags(): Promise<FeatureFlag[]> {
  const db = getExecutor();
  const rows = await db.all<Record<string, unknown>>("SELECT * FROM feature_flags ORDER BY sport_code, key");
  return rows as unknown as FeatureFlag[];
}

export async function listFeatureFlagsForSport(sportCode: string): Promise<FeatureFlag[]> {
  const db = getExecutor();
  const rows = await db.all<Record<string, unknown>>("SELECT * FROM feature_flags WHERE sport_code = ? ORDER BY key", [sportCode]);
  return rows as unknown as FeatureFlag[];
}

export async function getFeatureFlag(key: string): Promise<FeatureFlag | null> {
  const db = getExecutor();
  const row = await db.get<Record<string, unknown>>("SELECT * FROM feature_flags WHERE key = ?", [key]);
  return (row as unknown as FeatureFlag) ?? null;
}

export async function setFeatureFlagState(key: string, state: FeatureFlagState, updatedBy: string | null): Promise<void> {
  const db = getExecutor();
  await db.run("UPDATE feature_flags SET state = ?, updated_at = ?, updated_by = ? WHERE key = ?", [
    state,
    new Date().toISOString(),
    updatedBy,
    key,
  ]);
}
