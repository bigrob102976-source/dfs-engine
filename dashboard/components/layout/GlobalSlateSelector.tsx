"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { writeStoredSlateId } from "@/lib/globalSlateStorage";
import type { SlateOption } from "@/lib/orchestrator/types";
import { formatSlateLabel } from "@/lib/slateFilters";

/** Milestone 26's ONE global slate control -- lives in the top
 * navigation on every /dashboard/* page (see layout.tsx), drives the
 * `?slate=<id>` URL query param every slate-aware page reads via
 * lib/slateContext.ts::resolveSlateContext(). Selecting a slate here
 * updates the URL (preserving the current path and any other query
 * params) and Next.js re-renders every Server Component page against
 * the new selection -- no client-side state duplication needed.
 *
 * "Full Day (All Games)" is always the first option and is what an
 * absent/cleared `?slate=` param means -- selecting a slate is an
 * explicit user action, never auto-picked (see resolveSlateContext's
 * own docstring). */
export function GlobalSlateSelector({ slates }: { slates: SlateOption[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const selectedSlateId = searchParams.get("slate") ?? "";

  function handleChange(nextSlateId: string) {
    // Milestone 32.6: an explicit "Full Day (All Games)" choice clears
    // the stored preference too, so GlobalSlateSync never re-restores
    // the slate the user just backed out of on the next navigation.
    writeStoredSlateId(nextSlateId || null);
    const params = new URLSearchParams(searchParams.toString());
    if (nextSlateId) {
      params.set("slate", nextSlateId);
    } else {
      params.delete("slate");
    }
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }

  if (slates.length === 0) {
    return <span className="text-[11px] text-text-faint">No DK slates loaded</span>;
  }

  return (
    <label className="flex items-center gap-1.5 text-[11px] text-text-faint">
      Slate:
      <select
        aria-label="Selected slate"
        value={selectedSlateId}
        onChange={(e) => handleChange(e.target.value)}
        className="max-w-[220px] rounded border border-border bg-bg-panel-raised px-2 py-1 text-xs text-text"
      >
        <option value="">Full Day (All Games)</option>
        {slates.map((s) => (
          <option key={s.slateId} value={s.slateId}>
            {formatSlateLabel(s)}
          </option>
        ))}
      </select>
    </label>
  );
}
