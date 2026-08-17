"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PrimaryButton, SecondaryButton } from "@/components/ui/Button";

interface PlanOption {
  id: string;
  name: string;
  price_cents: number;
  billing_interval: "WEEKLY" | "MONTHLY";
  trial_days: number;
}

export function SubscribeButton({ plan }: { plan: PlanOption }) {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/account/billing/subscribe", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ planId: plan.id }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? "Something went wrong.");
        setSubmitting(false);
        return;
      }
      router.refresh();
    } catch {
      setError("Something went wrong.");
      setSubmitting(false);
    }
  }

  return (
    <div>
      <PrimaryButton onClick={handleClick} disabled={submitting} className="w-full py-2 text-sm">
        {submitting ? "Starting trial..." : `Start ${plan.trial_days}-day free trial`}
      </PrimaryButton>
      {error && <p className="mt-2 text-xs text-red">{error}</p>}
    </div>
  );
}

export function CancelButton() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConfirm() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/account/billing/cancel", { method: "POST" });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? "Something went wrong.");
        setSubmitting(false);
        return;
      }
      setConfirming(false);
      router.refresh();
    } catch {
      setError("Something went wrong.");
      setSubmitting(false);
    }
  }

  if (confirming) {
    return (
      <div className="rounded border border-red/40 bg-red/10 p-3">
        <p className="mb-2 text-xs text-text">Cancel your membership? You&apos;ll keep access until the end of the current billing period.</p>
        <div className="flex gap-2">
          <SecondaryButton onClick={() => setConfirming(false)} disabled={submitting} className="text-xs">
            Keep membership
          </SecondaryButton>
          <PrimaryButton onClick={handleConfirm} disabled={submitting} className="bg-red text-xs hover:bg-red">
            {submitting ? "Canceling..." : "Yes, cancel"}
          </PrimaryButton>
        </div>
        {error && <p className="mt-2 text-xs text-red">{error}</p>}
      </div>
    );
  }

  return (
    <SecondaryButton onClick={() => setConfirming(true)} className="text-xs">
      Cancel membership
    </SecondaryButton>
  );
}
