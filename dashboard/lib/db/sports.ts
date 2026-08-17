import { getDb } from "./client";
import type { Sport, SportStatus } from "./types";

export function listSports(): Sport[] {
  const db = getDb();
  const rows = db.prepare("SELECT * FROM sports ORDER BY sort_order ASC").all();
  return rows as unknown as Sport[];
}

export function getSport(code: string): Sport | null {
  const db = getDb();
  const row = db.prepare("SELECT * FROM sports WHERE code = ?").get(code);
  return (row as unknown as Sport) ?? null;
}

export function setSportStatus(code: string, status: SportStatus): void {
  const db = getDb();
  db.prepare("UPDATE sports SET status = ? WHERE code = ?").run(status, code);
}
