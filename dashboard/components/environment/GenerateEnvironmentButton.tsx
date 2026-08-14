"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PrimaryButton } from "@/components/ui/Button";

/** Triggers scripts/build_game_environment_report.py for today's slate via
 * POST /api/game-environment/generate, then revalidates the current route
 * so the Server Component page picks up the new snapshot -- same
 * one-shot-script-then-refresh shape as MissingDataState, but scoped to
 * this one independent script instead of the full refresh orchestrator. */
export function GenerateEnvironmentButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/game-environment/generate", { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error ?? "Failed to generate the environment report.");
        return;
      }
      router.refresh();
    } catch {
      setError("Failed to generate -- is the dashboard server running?");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-center gap-2">
      <PrimaryButton onClick={handleClick} disabled={busy} className="uppercase tracking-wide">
        {busy ? "Generating..." : "Generate Environment Report"}
      </PrimaryButton>
      {error && <p className="text-xs text-red">{error}</p>}
    </div>
  );
}
