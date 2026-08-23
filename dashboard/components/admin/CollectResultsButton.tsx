"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PrimaryButton } from "@/components/ui/Button";

/** Milestone 32.5 -- the "COLLECT RESULTS" admin action. Checks MLB
 * FINAL status, collects + scores whatever games are final, grades
 * every player and every saved M32.4 lineup, persists one immutable
 * ml_forward_results document. Safe to click repeatedly -- a slate
 * that isn't fully final yet still runs and reports PARTIAL results
 * honestly (see app/api/admin/ml-forward-results/collect/route.ts). */
export function CollectResultsButton({ date, slateId }: { date: string; slateId: string }) {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastStatus, setLastStatus] = useState<string | null>(null);

  async function handleClick() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/admin/ml-forward-results/collect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date, slateId }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? "Collection failed.");
        setSubmitting(false);
        return;
      }
      setLastStatus((body.status?.status as string) ?? "ok");
      setSubmitting(false);
      router.refresh();
    } catch {
      setError("Collection failed.");
      setSubmitting(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <PrimaryButton onClick={handleClick} disabled={submitting} className="text-xs uppercase tracking-wide">
        {submitting ? "Collecting..." : "Collect Results"}
      </PrimaryButton>
      {lastStatus && !error && <span className="text-[11px] text-text-faint">Last run: {lastStatus}</span>}
      {error && <p className="text-[11px] text-red">{error}</p>}
    </div>
  );
}
