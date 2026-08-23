"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";

import { readStoredSlateId, writeStoredSlateId } from "@/lib/globalSlateStorage";

/** Milestone 32.6 -- GLOBAL SLATE CONTEXT, restore half. Mounted once in
 * the dashboard layout. Every /dashboard/* page already resolves
 * "?slate=<id>" server-side via lib/slateContext.ts::resolveSlateContext
 * -- Sidebar/GlobalSlateSelector carry that param forward on ordinary
 * in-app navigation (see Sidebar.tsx), so this component's only job is
 * the two cases that DON'T already have a `?slate=` in the URL:
 *
 *   1. A page load/navigation that genuinely has no ?slate= yet (a
 *      bookmark, a fresh tab, a link that predates this milestone) --
 *      restore the last slate this browser explicitly selected.
 *   2. Whenever a slate IS present in the URL, remember it as the new
 *      "last selected" for next time.
 *
 * "URL wins" is enforced by construction: this effect only ever ADDS a
 * missing ?slate= parameter, never overwrites one that's already
 * present -- an explicit ?slate=X in the URL is never second-guessed.
 * Explicitly clearing to "Full Day" (GlobalSlateSelector) clears the
 * stored preference too (see lib/globalSlateStorage.ts), so backing out
 * to Full Day is never immediately re-restored by this effect. A stored
 * slate that's no longer valid for the resolved date is handled by
 * resolveSlateContext itself (an unmatched id resolves to "no slate
 * selected," never a silently wrong one) -- this component never
 * validates slate ids itself. */
export function GlobalSlateSync() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    const currentSlateId = searchParams?.get("slate");
    if (currentSlateId) {
      writeStoredSlateId(currentSlateId);
      return;
    }

    const stored = readStoredSlateId();
    if (!stored) return;

    const params = new URLSearchParams(searchParams?.toString() ?? "");
    params.set("slate", stored);
    router.replace(`${pathname}?${params.toString()}`);
    // Deliberately re-runs on every pathname/searchParams change (a
    // fresh navigation with no ?slate= should always trigger the
    // restore) -- once corrected, searchParams.get("slate") is truthy
    // and the early return above fires on the next run, so this never
    // loops.
  }, [pathname, searchParams, router]);

  return null;
}
