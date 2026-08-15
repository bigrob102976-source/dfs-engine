"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PrimaryButton } from "@/components/ui/Button";

function formatTimestamp(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

/** Top-right header controls: Refresh, Last Updated, Provider badge.
 * Refresh re-runs scripts/build_game_environment_report.py (same script
 * and route the Game Environment page already uses -- Vegas data lives
 * inside that same immutable snapshot, so no new script/route is
 * needed) then revalidates the route so the Server Component page picks
 * up the new snapshot. */
export function VegasHeaderActions({
  generatedAt,
  providerName,
  isMock,
}: {
  generatedAt: string | null;
  providerName: string | null;
  isMock: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRefresh() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/game-environment/generate", { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error ?? "Failed to refresh Vegas data.");
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
      <div className="flex items-center gap-2">
        {providerName && (
          <span
            className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
              isMock ? "bg-yellow/15 text-yellow" : "bg-gold/15 text-gold"
            }`}
          >
            {providerName}
          </span>
        )}
        <PrimaryButton onClick={handleRefresh} disabled={busy} className="uppercase tracking-wide">
          {busy ? "Refreshing..." : "Refresh"}
        </PrimaryButton>
      </div>
      <span className="text-[11px] text-text-faint">Last Updated: {formatTimestamp(generatedAt)}</span>
      {error && <p className="text-xs text-red">{error}</p>}
    </div>
  );
}
