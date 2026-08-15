"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

/** Quick Action: re-runs just the Pitcher/Batter Agent steps
 * (missing-data-only "smart" mode, same request shape
 * SlateReadiness.tsx already uses) rather than the full pipeline --
 * keeps this action's backend cost proportional to what it actually
 * asked for. */
export function RefreshResearchButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  function handleClick() {
    setBusy(true);
    fetch("/api/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ targetSteps: ["pitchers", "batters"], smart: true }),
    })
      .then(() => router.refresh())
      .finally(() => setBusy(false));
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={busy}
      className="flex w-full items-center justify-between rounded-[var(--radius-control)] border border-border-subtle bg-bg-panel-raised px-3 py-2 text-left text-xs text-text-muted transition-colors duration-150 hover:border-accent hover:text-text disabled:cursor-not-allowed disabled:opacity-60"
    >
      <span>Refresh Research</span>
      <span aria-hidden="true">{busy ? "⟳" : "→"}</span>
    </button>
  );
}
