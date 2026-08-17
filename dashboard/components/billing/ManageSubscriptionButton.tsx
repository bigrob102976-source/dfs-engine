"use client";

import { useState } from "react";

import { SecondaryButton } from "@/components/ui/Button";

export function ManageSubscriptionButton() {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/billing/portal", { method: "POST" });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? "Billing portal is not available right now.");
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
      <SecondaryButton onClick={handleClick} disabled={submitting} className="text-xs">
        {submitting ? "Opening..." : "Manage Subscription"}
      </SecondaryButton>
      {error && <p className="mt-2 text-xs text-red">{error}</p>}
    </div>
  );
}
