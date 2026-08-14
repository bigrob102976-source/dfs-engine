/** Mirror of external_projections/csv_import/providers.py's IMPORT_PROVIDERS
 * table -- the Import Projections wizard's Step 1 dropdown (Milestone 18).
 * A fixed, publicly-documented label list (not business logic Python
 * computes), so duplicating it here for the client-side dropdown is
 * low-risk -- same rationale as lib/dkRosterRules.ts mirroring
 * config/dk_roster_config.py. The actual provider key sent to the server
 * is validated again there against this same list before it ever reaches
 * a Python subprocess. */

export interface ImportProviderOption {
  key: string;
  label: string;
}

export const IMPORT_PROVIDERS: ImportProviderOption[] = [
  { key: "bluecollar", label: "BlueCollar DFS" },
  { key: "fantasycruncher", label: "FantasyCruncher" },
  { key: "sabersim", label: "SaberSim" },
  { key: "thebat", label: "THE BAT" },
  { key: "stokastic", label: "Stokastic" },
  { key: "rotogrinders", label: "RotoGrinders" },
  { key: "custom_csv", label: "Custom CSV" },
];

const _BY_KEY = new Map(IMPORT_PROVIDERS.map((p) => [p.key, p]));

export function isKnownImportProvider(key: string): boolean {
  return _BY_KEY.has(key);
}

export function importProviderLabel(key: string): string | null {
  return _BY_KEY.get(key)?.label ?? null;
}
