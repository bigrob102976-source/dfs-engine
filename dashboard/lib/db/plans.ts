import { getDb } from "./client";
import type { Plan } from "./types";

export function listActivePlans(): Plan[] {
  const db = getDb();
  const rows = db.prepare("SELECT * FROM plans WHERE is_active = 1 ORDER BY price_cents ASC").all();
  return rows as unknown as Plan[];
}

export function listAllPlans(): Plan[] {
  const db = getDb();
  const rows = db.prepare("SELECT * FROM plans ORDER BY price_cents ASC").all();
  return rows as unknown as Plan[];
}

export function getPlan(id: string): Plan | null {
  const db = getDb();
  const row = db.prepare("SELECT * FROM plans WHERE id = ?").get(id);
  return (row as unknown as Plan) ?? null;
}
