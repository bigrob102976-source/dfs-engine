import { getExecutor } from "./executor";
import type { Plan } from "./types";

export async function listActivePlans(): Promise<Plan[]> {
  const db = getExecutor();
  const rows = await db.all<Record<string, unknown>>("SELECT * FROM plans WHERE is_active = 1 ORDER BY price_cents ASC");
  return rows as unknown as Plan[];
}

export async function listAllPlans(): Promise<Plan[]> {
  const db = getExecutor();
  const rows = await db.all<Record<string, unknown>>("SELECT * FROM plans ORDER BY price_cents ASC");
  return rows as unknown as Plan[];
}

export async function getPlan(id: string): Promise<Plan | null> {
  const db = getExecutor();
  const row = await db.get<Record<string, unknown>>("SELECT * FROM plans WHERE id = ?", [id]);
  return (row as unknown as Plan) ?? null;
}
