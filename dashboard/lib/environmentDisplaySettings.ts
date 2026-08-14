"use client";

import { useCallback, useEffect, useState } from "react";

export interface EnvironmentSections {
  weather: boolean;
  vegas: boolean;
  bullpen: boolean;
  park: boolean;
  travel: boolean;
}

/** Mirrors config/game_environment_config.py's DEFAULT_ENABLED_SECTIONS --
 * this is a client-side rendering preference only, never the provider
 * on/off state the Python engine actually resolves at build time. */
export const DEFAULT_ENVIRONMENT_SECTIONS: EnvironmentSections = {
  weather: true,
  vegas: true,
  bullpen: true,
  park: true,
  travel: true,
};

const STORAGE_KEY = "bigmoney-environment-sections";

function readStored(): EnvironmentSections {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_ENVIRONMENT_SECTIONS;
    const parsed = JSON.parse(raw) as Partial<EnvironmentSections>;
    return { ...DEFAULT_ENVIRONMENT_SECTIONS, ...parsed };
  } catch {
    return DEFAULT_ENVIRONMENT_SECTIONS;
  }
}

/** Weather/Vegas/Bullpen/Park/Travel section visibility, persisted to
 * localStorage and shared between the Settings page's toggle UI
 * (components/environment/EnvironmentSectionToggles.tsx) and the
 * /dashboard/environment page/drawer that reads them -- same
 * independent-per-mount localStorage pattern as ThemeProvider and
 * Sidebar's collapse state. Umpire has no toggle here: it's always shown,
 * matching the milestone's "never guess, always show status" stance. */
export function useEnvironmentSections(): [EnvironmentSections, (key: keyof EnvironmentSections, value: boolean) => void] {
  const [sections, setSections] = useState<EnvironmentSections>(DEFAULT_ENVIRONMENT_SECTIONS);

  // Deferred one microtask so the setState call happens inside a callback
  // rather than the effect's synchronous body -- satisfies
  // react-hooks/set-state-in-effect (see ThemeProvider.tsx/Sidebar.tsx).
  useEffect(() => {
    Promise.resolve().then(() => setSections(readStored()));
  }, []);

  const setSection = useCallback((key: keyof EnvironmentSections, value: boolean) => {
    setSections((prev) => {
      const next = { ...prev, [key]: value };
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // Storage unavailable -- preference still applies for this session.
      }
      return next;
    });
  }, []);

  return [sections, setSection];
}
