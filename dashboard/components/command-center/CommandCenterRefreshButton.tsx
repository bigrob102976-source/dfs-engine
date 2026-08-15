"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PrimaryButton } from "@/components/ui/Button";

/** Header "Refresh" action -- POSTs the exact same /api/refresh the
 * existing RefreshPanel further down the page already uses (Milestone
 * 13's orchestrator), then revalidates the route. No new pipeline, no
 * new backend cost -- this is just a second, more prominent entry point
 * into the one that already exists. */
export function CommandCenterRefreshButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRefresh() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/refresh", { method: "POST" });
      if (res.status !== 409 && !res.ok) {
        setError("Failed to start the refresh.");
        return;
      }
      router.refresh();
    } catch {
      setError("Failed to refresh -- is the dashboard server running?");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <PrimaryButton onClick={handleRefresh} disabled={busy} className="uppercase tracking-wide">
        {busy ? "Refreshing..." : "Refresh"}
      </PrimaryButton>
      {error && <p className="text-[11px] text-red">{error}</p>}
    </div>
  );
}
