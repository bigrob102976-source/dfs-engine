"use client";

import type { VegasDisplaySettings } from "@/lib/vegasDisplaySettings";

const TOGGLES: Array<{ key: keyof VegasDisplaySettings; label: string }> = [
  { key: "showOpeningLines", label: "Show Opening Lines" },
  { key: "showMovementPercent", label: "Show Movement %" },
  { key: "showSparklines", label: "Show Sparklines" },
  { key: "compactMode", label: "Compact Mode" },
];

/** Show Opening Lines / Show Movement % / Show Sparklines / Compact
 * Mode -- a display preference only, persisted in this browser (see
 * lib/vegasDisplaySettings.ts). Never changes what data the engine
 * collects. Mirrors components/environment/EnvironmentSectionToggles.tsx's
 * markup exactly. */
export function VegasSettingsToggles({
  settings,
  onChange,
}: {
  settings: VegasDisplaySettings;
  onChange: (key: keyof VegasDisplaySettings, value: boolean) => void;
}) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5">
      {TOGGLES.map((t) => (
        <label key={t.key} className="flex items-center gap-1.5 text-xs text-text-muted">
          <input type="checkbox" className="accent-accent" checked={settings[t.key]} onChange={(e) => onChange(t.key, e.target.checked)} />
          {t.label}
        </label>
      ))}
    </div>
  );
}
