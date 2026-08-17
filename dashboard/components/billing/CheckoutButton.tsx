"use client";

import { useState } from "react";

import { PrimaryButton } from "@/components/ui/Button";

/** POSTs to /api/billing/checkout and does a full browser redirect to
 * the returned URL (a real Stripe Checkout page, or the dev provider's
 * own /subscribe/success) -- never router.push(), since Checkout is an
 * external, Stripe-hosted page. */
export function CheckoutButton({ planId, label }: { planId: string; label: string }) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/billing/checkout", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ planId }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? "Something went wrong. Please try again.");
        setSubmitting(false);
        return;
      }
      window.location.href = body.url;
    } catch {
      setError("Something went wrong. Please try again.");
      setSubmitting(false);
    }
  }

  return (
    <div>
      <PrimaryButton onClick={handleClick} disabled={submitting} className="w-full py-2.5 text-sm">
        {submitting ? "Redirecting to secure checkout..." : label}
      </PrimaryButton>
      {error && <p className="mt-2 text-xs text-red">{error}</p>}
    </div>
  );
}
