// NFL UI M1 -- honest null-formatting helpers, mirroring the MLB
// optimizer's fmt() convention (components/optimizer/PoolTable.tsx):
// a real "not available" value renders as "--", never 0, never the
// literal string "null"/"undefined".

export function fmt(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return value.toFixed(digits);
}

export function fmtSalary(value: number | null | undefined): string {
  if (value === null || value === undefined) return "--";
  return `$${value.toLocaleString()}`;
}

export function fmtPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return `${(value * 100).toFixed(digits)}%`;
}

export function fmtValue(projection: number | null | undefined, salary: number): string {
  if (projection === null || projection === undefined || !salary) return "--";
  return (projection / (salary / 1000)).toFixed(2);
}

export function identityLabel(row: { is_team_entity: boolean; identity_resolved: boolean }): string {
  if (row.is_team_entity) return "Team";
  return row.identity_resolved ? "Resolved" : "Identity Unresolved";
}

export function projectionLabel(source: string | null | undefined): string {
  if (!source) return "No Projection";
  if (source.includes("BASELINE")) return "BIG MONEY NATIVE DST BASELINE";
  if (source === "BIG_MONEY_NATIVE") return "BIG MONEY NATIVE";
  return source.replace(/_/g, " ");
}
