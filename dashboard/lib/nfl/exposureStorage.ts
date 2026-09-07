"use client";

// NFL M13 -- per-player min/max exposure overrides, keyed by
// DraftKings player identity, persisted per-slate to localStorage.
// Mirrors lib/nfl/lockExcludeStorage.ts's exact pattern and per-slate
// key discipline. Fractions are stored as 0.0-1.0 (matching the
// backend contract, nfl/optimizer_models.py::NflOptimizerSettings) --
// the UI itself displays/collects whole percentages and converts.

export interface ExposureState {
  maxExposure: Record<string, number>; // draftkings_player_id -> fraction 0.0-1.0
  minExposure: Record<string, number>;
}

const EMPTY_STATE: ExposureState = { maxExposure: {}, minExposure: {} };

function key(draftGroupId: number): string {
  return `bigmoney-nfl-exposure-${draftGroupId}`;
}

export function loadExposureState(draftGroupId: number): ExposureState {
  if (typeof window === "undefined") return { ...EMPTY_STATE };
  try {
    const raw = window.localStorage.getItem(key(draftGroupId));
    if (!raw) return { maxExposure: {}, minExposure: {} };
    const parsed = JSON.parse(raw);
    return {
      maxExposure: parsed.maxExposure && typeof parsed.maxExposure === "object" ? parsed.maxExposure : {},
      minExposure: parsed.minExposure && typeof parsed.minExposure === "object" ? parsed.minExposure : {},
    };
  } catch {
    return { maxExposure: {}, minExposure: {} };
  }
}

export function saveExposureState(draftGroupId: number, state: ExposureState): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key(draftGroupId), JSON.stringify(state));
  } catch {
    // best-effort only -- a full/blocked localStorage should never crash the page
  }
}
