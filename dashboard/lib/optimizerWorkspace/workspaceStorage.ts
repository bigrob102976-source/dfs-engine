// UI-preference persistence for the interactive optimizer workspace
// (Milestone 14's "STATE PERSISTENCE" requirement). localStorage only
// ever holds slate selection / lock-exclude-exposure/stack/objective
// choices -- never provider credentials or anything server-secret (see
// dfs/providers/config.py -- API keys never leave the server process).

import type { ProjectionSource } from "./types";

const STORAGE_KEY = "mlb-dfs-optimizer-workspace-v1";

export interface PersistedWorkspaceState {
  selectedSlateId: string | null;
  // Milestone 31.2C. Optional so state persisted before this milestone
  // still loads cleanly -- absent means "no explicit date," which
  // resolves to Chicago-today exactly like before this milestone.
  selectedDate?: string | null;
  locks: string[];
  exclusions: string[];
  maxExposure: Record<string, number>;
  stackSize: number | null;
  stackTeam: string | null;
  // Multi-team stacks (M2). Optional so state persisted before this
  // milestone still loads cleanly -- absent means null/null, identical
  // to a brand-new session (no secondary stack).
  stackSize2?: number | null;
  stackTeam2?: string | null;
  allowPitcherVsHitter: boolean;
  // PROBABLE FIX milestone. Optional so state persisted before this
  // milestone still loads cleanly -- callers must default to true
  // ("ON by default") when absent.
  useProbableStarters?: boolean;
  minSalary: number | null;
  minUnique: number;
  lineups: number;
  objective: "projection" | "ceiling" | "balanced" | "leverage";
  // Milestone 17. Optional so state persisted before this milestone still
  // loads cleanly -- callers must default both when absent.
  projectionSource?: ProjectionSource;
  showProjectionComparison?: boolean;
  // T1C -- ADMIN-only "Canonical Postgres Test" mode. Optional so state
  // persisted before this milestone still loads cleanly (absent means
  // legacy, exactly like before). Restoring `true` for a user who is no
  // longer authorized (flag flipped, or a MEMBER somehow had it in
  // localStorage) is harmless: the server re-checks authorization on
  // every request (see lib/servingBackend/config.ts) and silently
  // downgrades, it never trusts this persisted value alone.
  canonicalTestMode?: boolean;
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
