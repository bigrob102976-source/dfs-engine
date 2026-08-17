import type { ReactNode } from "react";

/** Shared centered-card shell for every auth page (/login, /signup,
 * /forgot-password, /reset-password, /verify-email) -- mirrors the
 * exact markup the original single-shared-password /login page used. */
export function AuthCard({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-bg">
      <div className="w-full max-w-sm rounded-2xl border border-border bg-bg-panel p-8 shadow-[var(--shadow-card)]">
        <div className="mb-6">
          <h1 className="text-lg font-semibold tracking-tight text-text">
            BIG MONEY <span className="text-gold">DFS</span>
          </h1>
          <p className="text-[11px] uppercase tracking-widest text-text-faint">AI Research Terminal</p>
        </div>
        {children}
      </div>
    </div>
  );
}

export const AUTH_INPUT_CLASS =
  "mb-4 w-full rounded border border-border bg-bg-panel-raised px-3 py-2 text-sm text-text outline-none focus:border-accent";
export const AUTH_LABEL_CLASS = "mb-1 block text-xs text-text-muted";
