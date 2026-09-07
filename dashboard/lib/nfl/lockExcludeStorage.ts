"use client";

// NFL UI M1 -- lock/exclude state, keyed by DraftKings player identity
// (draftkings_player_id), persisted per-slate to localStorage. Mirrors
// the MLB optimizer workspace's own "DK id is only unique within one
// slate" discipline (lib/optimizerWorkspace/workspaceStorage.ts) --
// switching slates resets the set.

interface LockExcludeState {
  locks: string[];
  excludes: string[];
}

function key(draftGroupId: number): string {
  return `bigmoney-nfl-locks-${draftGroupId}`;
}

export function loadLockExcludeState(draftGroupId: number): LockExcludeState {
  if (typeof window === "undefined") return { locks: [], excludes: [] };
  try {
    const raw = window.localStorage.getItem(key(draftGroupId));
    if (!raw) return { locks: [], excludes: [] };
    const parsed = JSON.parse(raw);
    return {
      locks: Array.isArray(parsed.locks) ? parsed.locks : [],
      excludes: Array.isArray(parsed.excludes) ? parsed.excludes : [],
    };
  } catch {
    return { locks: [], excludes: [] };
  }
}

export function saveLockExcludeState(draftGroupId: number, state: LockExcludeState): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key(draftGroupId), JSON.stringify(state));
  } catch {
    // best-effort only -- a full/blocked localStorage should never crash the page
  }
}
