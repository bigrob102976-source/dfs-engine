import crypto from "node:crypto";

import { getExecutor } from "./executor";
import type { NflSavedLineupRow } from "./types";

/** NFL M14 -- CRUD for saved NFL lineups (see migrations/0009_nfl_
 * saved_lineups.sql's docstring for the storage-shape rationale).
 * Mutable rows, unlike this project's research/ML snapshot artifacts --
 * late swap updates slots_json/updated_at in place, id unchanged. */

export async function createSavedLineup(args: {
  userId: string;
  draftGroupId: number;
  slateDate: string;
  mode: string;
  stackConfigJson: string;
  slotsJson: string;
}): Promise<NflSavedLineupRow> {
  const db = getExecutor();
  const id = crypto.randomUUID();
  const now = new Date().toISOString();
  await db.run(
    `INSERT INTO nfl_saved_lineups (id, user_id, draft_group_id, slate_date, mode, stack_config_json, slots_json, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [id, args.userId, args.draftGroupId, args.slateDate, args.mode, args.stackConfigJson, args.slotsJson, now, now],
  );
  return (await getSavedLineupById(id))!;
}

export async function getSavedLineupById(id: string): Promise<NflSavedLineupRow | null> {
  const db = getExecutor();
  const row = await db.get<Record<string, unknown>>("SELECT * FROM nfl_saved_lineups WHERE id = ?", [id]);
  return (row as unknown as NflSavedLineupRow) ?? null;
}

export async function listSavedLineups(userId: string, draftGroupId: number): Promise<NflSavedLineupRow[]> {
  const db = getExecutor();
  const rows = await db.all<Record<string, unknown>>(
    "SELECT * FROM nfl_saved_lineups WHERE user_id = ? AND draft_group_id = ? ORDER BY created_at DESC",
    [userId, draftGroupId],
  );
  return rows as unknown as NflSavedLineupRow[];
}

/** Late swap's write path -- replaces slots_json (the whole slot array,
 * locked slots included unchanged) and bumps updated_at. Never touches
 * id/user_id/draft_group_id/slate_date/created_at. */
export async function updateSavedLineupSlots(id: string, slotsJson: string): Promise<NflSavedLineupRow | null> {
  const db = getExecutor();
  const now = new Date().toISOString();
  await db.run("UPDATE nfl_saved_lineups SET slots_json = ?, updated_at = ? WHERE id = ?", [slotsJson, now, id]);
  return getSavedLineupById(id);
}

export async function deleteSavedLineup(id: string, userId: string): Promise<boolean> {
  const db = getExecutor();
  const existing = await getSavedLineupById(id);
  if (!existing || existing.user_id !== userId) return false;
  await db.run("DELETE FROM nfl_saved_lineups WHERE id = ?", [id]);
  return true;
}
