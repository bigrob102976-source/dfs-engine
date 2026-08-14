"use client";

import { useEffect } from "react";
import type { ReactNode } from "react";

/** Centered dialog on a dim backdrop. Closes on backdrop click or Escape. */
export function Modal({ onClose, children, ariaLabel }: { onClose: () => void; children: ReactNode; ariaLabel: string }) {
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-[var(--radius-card)] border border-border bg-bg-panel p-5 shadow-[var(--shadow-popover)]"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel}
      >
        {children}
      </div>
    </div>
  );
}
