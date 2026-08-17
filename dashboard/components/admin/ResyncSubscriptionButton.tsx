"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { SecondaryButton } from "@/components/ui/Button";

/** The only admin action that touches Stripe -- and it's read-only from
 * Stripe's perspective (re-fetch + reconcile), never a database-only
 * fabricated status change. See app/api/admin/subscriptions/[id]/resync/route.ts. */
export function ResyncSubscriptionButton({ subscriptionId }: { subscriptionId: string }) {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`/api/admin/subscriptions/${subscriptionId}/resync`, { method: "POST" });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? "Resync failed.");
        setSubmitting(false);
        return;
      }
      router.refresh();
    } catch {
      setError("Resync failed.");
      setSubmitting(false);
    }
  }

  return (
    <div>
      <SecondaryButton onClick={handleClick} disabled={submitting} className="text-xs">
        {submitting ? "Resyncing..." : "Resync from Stripe"}
      </SecondaryButton>
      {error && <p className="mt-1 text-[11px] text-red">{error}</p>}
    </div>
  );
}
