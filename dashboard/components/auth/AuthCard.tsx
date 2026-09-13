import type { ReactNode } from "react";

import { Footer } from "@/components/Footer";

/** Shared centered-card shell for every auth page (/login, /signup,
 * /forgot-password, /reset-password, /verify-email) -- mirrors the
 * exact markup the original single-shared-password /login page used.
 * Sprint 1 (2026-09-13): wrapped in a column with <Footer/> pinned below
 * the centered card so legal/trust links reach a visitor before they
 * even have an account. */
export function AuthCard({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <div className="flex flex-1 items-center justify-center">
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
      <Footer />
    </div>
  );
}

export const AUTH_INPUT_CLASS =
  "mb-4 w-full rounded border border-border bg-bg-panel-raised px-3 py-2 text-sm text-text outline-none focus:border-accent";
export const AUTH_LABEL_CLASS = "mb-1 block text-xs text-text-muted";
