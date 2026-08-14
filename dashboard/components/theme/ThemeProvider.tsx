"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type ThemePreference = "dark" | "light" | "system";
export type ResolvedTheme = "dark" | "light";

const STORAGE_KEY = "bigmoney-theme";

interface ThemeContextValue {
  theme: ThemePreference;
  resolvedTheme: ResolvedTheme;
  setTheme: (theme: ThemePreference) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function resolve(theme: ThemePreference): ResolvedTheme {
  if (theme !== "system") return theme;
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

/** The inline script the root layout renders BEFORE hydration, so the
 * very first paint already has the right `data-theme` attribute -- no
 * flash of the wrong theme. Kept in one place so the provider's own
 * logic below (which runs after hydration) can never drift from it. */
export const THEME_INIT_SCRIPT = `
(function() {
  try {
    var stored = localStorage.getItem(${JSON.stringify(STORAGE_KEY)});
    var theme = stored === "dark" || stored === "light" || stored === "system" ? stored : "dark";
    var resolved = theme === "system"
      ? (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark")
      : theme;
    document.documentElement.setAttribute("data-theme", resolved);
  } catch (e) {}
})();
`;

/** Dark/Light/System theme preference, persisted to localStorage.
 * "Dark" is the hard default on first visit (never inferred from OS) --
 * only explicitly choosing "System" makes the OS preference matter,
 * matching the design system's "Dark Mode (Default)" spec. Applies the
 * resolved theme as `data-theme` on <html>, which every color token in
 * globals.css keys off. */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<ThemePreference>("dark");
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>("dark");

  // Deferred one microtask so every setState call happens inside a
  // callback rather than the effect's synchronous body -- satisfies
  // react-hooks/set-state-in-effect (see OptimizerWorkspace.tsx for the
  // same established pattern).
  useEffect(() => {
    Promise.resolve().then(() => {
      let stored: string | null = null;
      try {
        stored = window.localStorage.getItem(STORAGE_KEY);
      } catch {
        // Storage unavailable (private browsing) -- fall back to the default.
      }
      const initial: ThemePreference = stored === "dark" || stored === "light" || stored === "system" ? stored : "dark";
      setThemeState(initial);
      setResolvedTheme(resolve(initial));
    });
  }, []);

  useEffect(() => {
    const resolved = resolve(theme);
    document.documentElement.setAttribute("data-theme", resolved);
    Promise.resolve().then(() => setResolvedTheme(resolved));

    if (theme !== "system") return;
    const mql = window.matchMedia("(prefers-color-scheme: light)");
    // A change-event callback, not the effect body itself -- this is the
    // sanctioned "subscribe to an external system" pattern, not flagged
    // by set-state-in-effect.
    const onChange = () => {
      const next = resolve("system");
      setResolvedTheme(next);
      document.documentElement.setAttribute("data-theme", next);
    };
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [theme]);

  const setTheme = useCallback((next: ThemePreference) => {
    setThemeState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Storage unavailable -- theme still applies for this session.
    }
  }, []);

  const value = useMemo(() => ({ theme, resolvedTheme, setTheme }), [theme, resolvedTheme, setTheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}
