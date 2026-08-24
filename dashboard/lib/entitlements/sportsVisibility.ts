import { listSports } from "@/lib/db/sports";
import type { Sport } from "@/lib/db/types";

export async function listSportsForNav(): Promise<Sport[]> {
  return listSports();
}
