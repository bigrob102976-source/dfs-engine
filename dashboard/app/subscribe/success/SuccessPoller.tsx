"use client";

import { useEffect, useState } from "react";

import { PrimaryButton } from "@/components/ui/Button";

const POLL_INTERVAL_MS = 1500;
const MAX_ATTEMPTS = 8; // ~12s bounded window

type PollState = "polling" | "trialing" | "active" | "timeout";

const ACCESS_GRANTING_STATUSES = new Set(["trialing", "active", "complimentary"]);

/** "Finalizing Membership..." while polling GET /api/account for the
 * server-side subscription status Stripe's webhook writes asynchronously
 * -- landing on this page never itself grants access. On a bounded
 * timeout (webhook hasn't landed yet), shows a graceful "still
 * finalizing" state, never an error, since the subscription may simply
 * still be in flight. */
export function SuccessPoller() {
  const [state, setState] = useState<PollState>("polling");

  useEffect(() => {
    let cancelled = false;
    let attempts = 0;

    async function poll() {
      attempts += 1;
      try {
        const res = await fetch("/api/account");
        if (res.ok) {
          const body = await res.json();
          const status: string | undefined = body?.subscription?.status;
          if (!cancelled && status && ACCESS_GRANTING_STATUSES.has(status)) {
            setState(status === "trialing" ? "trialing" : "active");
            return;
          }
        }
      } catch {
        // Network hiccup -- keep polling within the bounded window.
      }
      if (cancelled) return;
      if (attempts >= MAX_ATTEMPTS) {
        setState("timeout");
        return;
      }
      setTimeout(poll, POLL_INTERVAL_MS);
    }

    poll();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state === "polling") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-bg text-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-border border-t-accent" aria-hidden="true" />
        <p className="text-sm text-text-muted">Finalizing Membership...</p>
      </div>
    );
  }

  if (state === "timeout") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-bg px-6 text-center">
        <p className="max-w-sm text-sm text-text-muted">
          Still finalizing -- this can take a few seconds. Refresh this page or check your billing status shortly.
        </p>
        <a href="/account/billing" className="text-sm text-accent hover:text-accent-hover">
          Check Account Billing →
        </a>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-bg px-6 text-center">
      <h1 className="text-2xl font-bold tracking-tight text-text">WELCOME TO BIG MONEY DFS</h1>
      <p className="text-sm font-medium text-green">{state === "trialing" ? "Trial Active" : "Membership Active"}</p>
      <a href="/dashboard" className="mt-2">
        <PrimaryButton className="px-6 py-2.5 text-sm">Enter Dashboard</PrimaryButton>
      </a>
    </div>
  );
}
