"use client";

import { useEffect } from "react";
import type { ReactNode } from "react";

/** Slide-out panel anchored to the right edge, on a dim backdrop.
 * Closes on backdrop click or Escape. The Player Detail Panel is the
 * canonical use -- any future detail/edit surface should use this
 * instead of hand-rolling another fixed-position overlay. */
export function Drawer({
  onClose,
  children,
  ariaLabel,
  width = "w-[440px]",
}: {
  onClose: () => void;
  children: ReactNode;
  ariaLabel: string;
  width?: string;
}) {
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/50 animate-[fade-in_150ms_ease-out]" onClick={onClose}>
      <div
        className={`h-full ${width} max-w-full overflow-y-auto border-l border-border bg-bg-panel p-5 shadow-[var(--shadow-popover)] animate-[slide-in_150ms_ease-out]`}
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
