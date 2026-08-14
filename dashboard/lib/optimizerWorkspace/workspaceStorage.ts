// UI-preference persistence for the interactive optimizer workspace
// (Milestone 14's "STATE PERSISTENCE" requirement). localStorage only
// ever holds slate selection / lock-exclude-exposure/stack/objective
// choices -- never provider credentials or anything server-secret (see
// dfs/providers/config.py -- API keys never leave the server process).

const STORAGE_KEY = "mlb-dfs-optimizer-workspace-v1";

export interface PersistedWorkspaceState {
  selectedSlateId: string | null;
  locks: string[];
  exclusions: string[];
  maxExposure: Record<string, number>;
  stackSize: number | null;
  stackTeam: string | null;
  allowPitcherVsHitter: boolean;
  minSalary: number | null;
  minUnique: number;
  lineups: number;
  objective: "projection" | "ceiling" | "balanced" | "leverage";
  // Milestone 17. Optional so state persisted before this milestone still
  // loads cleanly -- callers must default both when absent.
  projectionSource?: "independent" | "external" | "adjusted";
  showProjectionComparison?: boolean;
}

export function loadWorkspaceState(): PersistedWorkspaceState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PersistedWorkspaceState;
  } catch {
    return null;
  }
}

export function saveWorkspaceState(state: PersistedWorkspaceState): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Storage full/unavailable (private browsing, etc.) -- the workspace
    // still functions for the current session, it just won't persist.
  }
}
