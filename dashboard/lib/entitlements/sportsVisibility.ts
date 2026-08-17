import { listSports } from "@/lib/db/sports";
import type { Sport } from "@/lib/db/types";

export function listSportsForNav(): Sport[] {
  return listSports();
}
