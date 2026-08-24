import { getExecutor } from "./executor";
import type { Sport, SportStatus } from "./types";

export async function listSports(): Promise<Sport[]> {
  const db = getExecutor();
  const rows = await db.all<Record<string, unknown>>("SELECT * FROM sports ORDER BY sort_order ASC");
  return rows as unknown as Sport[];
}

export async function getSport(code: string): Promise<Sport | null> {
  const db = getExecutor();
  const row = await db.get<Record<string, unknown>>("SELECT * FROM sports WHERE code = ?", [code]);
  return (row as unknown as Sport) ?? null;
}

export async function setSportStatus(code: string, status: SportStatus): Promise<void> {
  const db = getExecutor();
  await db.run("UPDATE sports SET status = ? WHERE code = ?", [status, code]);
}
