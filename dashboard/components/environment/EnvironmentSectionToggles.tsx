"use client";

import { useEnvironmentSections, type EnvironmentSections } from "@/lib/environmentDisplaySettings";

const TOGGLES: Array<{ key: keyof EnvironmentSections; label: string }> = [
  { key: "weather", label: "Weather" },
  { key: "vegas", label: "Vegas" },
  { key: "bullpen", label: "Bullpen" },
  { key: "park", label: "Park" },
  { key: "travel", label: "Travel" },
];

/** Settings toggle for which Game Environment sections render on the
 * /dashboard/environment cards and detail drawer (Milestone DS2's
 * "Allow enabling/disabling ... from Settings" requirement). Purely a
 * display preference, persisted client-side -- flipping these never
 * changes which providers the Python engine calls or what a snapshot
 * contains. Umpire has no toggle: it always renders its KNOWN/UNKNOWN
 * status. */
export function EnvironmentSectionToggles() {
  const [sections, setSection] = useEnvironmentSections();

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-5">
      {TOGGLES.map(({ key, label }) => (
        <label
          key={key}
          className="flex items-center justify-between gap-2 rounded border border-border-subtle bg-bg-panel-raised px-3 py-2 text-xs text-text"
        >
          {label}
          <input
            type="checkbox"
            checked={sections[key]}
            onChange={(e) => setSection(key, e.target.checked)}
            className="h-3.5 w-3.5 accent-accent"
          />
        </label>
      ))}
    </div>
  );
}
