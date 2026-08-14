"use client";

import { useTheme, type ThemePreference } from "./ThemeProvider";

const OPTIONS: Array<{ value: ThemePreference; label: string; icon: string }> = [
  { value: "dark", label: "Dark", icon: "🌙" },
  { value: "light", label: "Light", icon: "☀" },
  { value: "system", label: "System", icon: "💻" },
];

/** Compact three-way theme switch for the top navigation. */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <div role="radiogroup" aria-label="Theme" className="flex items-center gap-0.5 rounded-lg border border-border bg-bg-panel-raised p-0.5">
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          role="radio"
          aria-checked={theme === opt.value}
          aria-label={`${opt.label} theme`}
          title={`${opt.label} theme`}
          onClick={() => setTheme(opt.value)}
          className={`flex h-6 w-6 items-center justify-center rounded-md text-[11px] transition-colors duration-150 ${
            theme === opt.value ? "bg-accent text-white" : "text-text-faint hover:text-text-muted"
          }`}
        >
          {opt.icon}
        </button>
      ))}
    </div>
  );
}
