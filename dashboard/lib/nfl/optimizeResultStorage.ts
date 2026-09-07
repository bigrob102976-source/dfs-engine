"use client";

import type { NflOptimizeResult } from "./types";

const KEY = "bigmoney-nfl-last-build";

export function saveOptimizeResult(draftGroupId: number, result: NflOptimizeResult): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify({ draftGroupId, result, savedAt: Date.now() }));
  } catch {
    // best-effort only
  }
}

export function loadOptimizeResult(draftGroupId: number): NflOptimizeResult | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed.draftGroupId !== draftGroupId) return null;
    return parsed.result as NflOptimizeResult;
  } catch {
    return null;
  }
}
