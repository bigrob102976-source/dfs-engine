import type { PlayerRow } from "./types";

export type SortDirection = "asc" | "desc";

/** Generic, stable-ish numeric/string sort by a top-level key. Nulls
 * always sort to the end regardless of direction (a missing value is
 * never "the best" or "the worst", just unknown). */
export function sortRows<T>(
  rows: T[],
  key: keyof T,
  direction: SortDirection,
): T[] {
  const withIndex = rows.map((row, i) => ({ row, i }));
  withIndex.sort((a, b) => {
    const av = a.row[key];
    const bv = b.row[key];
    const aNull = av === null || av === undefined;
    const bNull = bv === null || bv === undefined;
    if (aNull && bNull) return a.i - b.i;
    if (aNull) return 1;
    if (bNull) return -1;

    let cmp: number;
    if (typeof av === "string" && typeof bv === "string") {
      cmp = av.localeCompare(bv);
    } else {
      cmp = (av as number) < (bv as number) ? -1 : (av as number) > (bv as number) ? 1 : 0;
    }
    if (cmp === 0) return a.i - b.i;
    return direction === "asc" ? cmp : -cmp;
  });
  return withIndex.map((w) => w.row);
}

export interface PlayerRowFilters {
  team?: string;
  position?: string;
  ownershipTier?: string;
  minConfidence?: number;
  maxRisk?: number;
  tag?: string;
  stackTeam?: string;
  gameId?: string;
  minSalary?: number;
  maxSalary?: number;
  search?: string;
}

export function filterPlayerRows(rows: PlayerRow[], filters: PlayerRowFilters): PlayerRow[] {
  return rows.filter((row) => {
    if (filters.team && row.team !== filters.team) return false;
    if (filters.stackTeam && row.team !== filters.stackTeam) return false;
    if (filters.gameId && row.gameId !== filters.gameId) return false;
    if (filters.position && !row.positions.includes(filters.position) && row.position !== filters.position) {
      return false;
    }
    if (filters.ownershipTier && row.ownershipTier !== filters.ownershipTier) return false;
    if (filters.minConfidence !== undefined) {
      if (row.confidence === null || row.confidence < filters.minConfidence) return false;
    }
    if (filters.maxRisk !== undefined) {
      if (row.risk === null || row.risk > filters.maxRisk) return false;
    }
    if (filters.tag && !row.tags.includes(filters.tag)) return false;
    if (filters.minSalary !== undefined) {
      if (row.salary === null || row.salary < filters.minSalary) return false;
    }
    if (filters.maxSalary !== undefined) {
      if (row.salary === null || row.salary > filters.maxSalary) return false;
    }
    if (filters.search) {
      const q = filters.search.trim().toLowerCase();
      if (q && !row.name.toLowerCase().includes(q)) return false;
    }
    return true;
  });
}

export function distinctValues<T>(rows: T[], pick: (row: T) => string | null | undefined): string[] {
  const values = new Set<string>();
  for (const row of rows) {
    const v = pick(row);
    if (v) values.add(v);
  }
  return Array.from(values).sort();
}
