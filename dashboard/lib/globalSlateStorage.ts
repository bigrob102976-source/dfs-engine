// Milestone 32.6 -- GLOBAL SLATE CONTEXT localStorage persistence.
// Pure, client-safe (no node:fs) -- shared by GlobalSlateSelector
// (writes on explicit user choice) and GlobalSlateSync (writes on any
// URL that already carries a slate, reads to restore a missing one).

const STORAGE_KEY = "mlb-dfs-global-slate-v1";

export function readStoredSlateId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

/** `null` means "the user explicitly chose Full Day (All Games)" --
 * clears the stored preference so a later navigation that drops the
 * URL param is never silently re-restored to a slate the user just
 * backed out of. */
export function writeStoredSlateId(slateId: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (slateId) {
      window.localStorage.setItem(STORAGE_KEY, slateId);
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // Storage unavailable (private browsing, etc.) -- the slate choice
    // just won't survive a fresh navigation with no ?slate= at all;
    // every already-URL-qualified navigation still works without it.
  }
}
