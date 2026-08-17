import { getDb } from "./client";
import type { FeatureFlag, FeatureFlagState } from "./types";

export function listFeatureFlags(): FeatureFlag[] {
  const db = getDb();
  const rows = db.prepare("SELECT * FROM feature_flags ORDER BY sport_code, key").all();
  return rows as unknown as FeatureFlag[];
}

export function listFeatureFlagsForSport(sportCode: string): FeatureFlag[] {
  const db = getDb();
  const rows = db.prepare("SELECT * FROM feature_flags WHERE sport_code = ? ORDER BY key").all(sportCode);
  return rows as unknown as FeatureFlag[];
}

export function getFeatureFlag(key: string): FeatureFlag | null {
  const db = getDb();
  const row = db.prepare("SELECT * FROM feature_flags WHERE key = ?").get(key);
  return (row as unknown as FeatureFlag) ?? null;
}

export function setFeatureFlagState(key: string, state: FeatureFlagState, updatedBy: string | null): void {
  const db = getDb();
  db.prepare("UPDATE feature_flags SET state = ?, updated_at = ?, updated_by = ? WHERE key = ?").run(
    state,
    new Date().toISOString(),
    updatedBy,
    key,
  );
}
