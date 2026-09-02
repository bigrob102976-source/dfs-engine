import { getExecutor } from "./executor";

// M6: extracted from lib/servingBackend/canonicalPostgresBackend.ts (M5)
// so canonicalEligibility.ts (M6) can reuse the exact same batched
// mlbam-external-id lookup rather than duplicating it -- never a second,
// divergent implementation.
export async function resolveMlbPlayerIds(internalPlayerIds: string[]): Promise<Map<string, string>> {
  const distinct = [...new Set(internalPlayerIds)];
  if (distinct.length === 0) return new Map();
  const db = getExecutor();
  const placeholders = distinct.map(() => "?").join(", ");
  const rows = await db.all<{ internal_player_id: string; external_id: string }>(
    `SELECT internal_player_id, external_id FROM player_external_ids
     WHERE provider = 'mlbam' AND is_current = 1 AND internal_player_id IN (${placeholders})`,
    distinct,
  );
  const map = new Map<string, string>();
  for (const row of rows) map.set(row.internal_player_id, row.external_id);
  return map;
}
