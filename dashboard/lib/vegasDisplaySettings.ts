"use client";

import { useCallback, useEffect, useState } from "react";

export interface VegasDisplaySettings {
  showOpeningLines: boolean;
  showMovementPercent: boolean;
  showSparklines: boolean;
  compactMode: boolean;
}

export const DEFAULT_VEGAS_DISPLAY_SETTINGS: VegasDisplaySettings = {
  showOpeningLines: true,
  showMovementPercent: true,
  showSparklines: true,
  compactMode: false,
};

const STORAGE_KEY = "bigmoney-vegas-display-settings";

function readStored(): VegasDisplaySettings {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_VEGAS_DISPLAY_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<VegasDisplaySettings>;
    return { ...DEFAULT_VEGAS_DISPLAY_SETTINGS, ...parsed };
  } catch {
    return DEFAULT_VEGAS_DISPLAY_SETTINGS;
  }
}

/** Show Opening Lines / Show Movement % / Show Sparklines / Compact Mode
 * -- persisted to localStorage, same independent-per-mount pattern as
 * useEnvironmentSections (lib/environmentDisplaySettings.ts). Purely a
 * client-side rendering preference; never changes what data the engine
 * collects or how it's scored. */
export function useVegasDisplaySettings(): [VegasDisplaySettings, (key: keyof VegasDisplaySettings, value: boolean) => void] {
  const [settings, setSettings] = useState<VegasDisplaySettings>(DEFAULT_VEGAS_DISPLAY_SETTINGS);

  // Deferred one microtask so the setState call happens inside a callback
  // rather than the effect's synchronous body -- satisfies
  // react-hooks/set-state-in-effect (see useEnvironmentSections).
  useEffect(() => {
    Promise.resolve().then(() => setSettings(readStored()));
  }, []);

  const setSetting = useCallback((key: keyof VegasDisplaySettings, value: boolean) => {
    setSettings((prev) => {
      const next = { ...prev, [key]: value };
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // Storage unavailable -- preference still applies for this session.
      }
      return next;
    });
  }, []);

  return [settings, setSetting];
}
