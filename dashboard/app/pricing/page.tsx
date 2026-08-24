import Link from "next/link";

import { StripeTestModeBadge } from "@/components/billing/StripeTestModeBadge";
import { listActivePlans } from "@/lib/db/plans";
import type { Plan } from "@/lib/db/types";

export const dynamic = "force-dynamic";

const CTA_LINK_CLASS =
  "inline-flex w-full items-center justify-center gap-1.5 rounded-[var(--radius-control)] px-3.5 py-2.5 text-sm font-semibold text-white transition-colors duration-150 bg-accent hover:bg-accent-hover";

function formatPrice(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function PlanCard({ plan, bestValue }: { plan: Plan; bestValue: boolean }) {
  return (
    <div
      className={`relative flex flex-col rounded-[var(--radius-card)] border p-6 shadow-[var(--shadow-card)] ${
        bestValue ? "border-gold bg-bg-panel" : "border-border bg-bg-panel"
      }`}
    >
      {bestValue && (
        <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-gold px-3 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-bg">
          Best Value
        </span>
      )}
      <div className="text-xs font-semibold uppercase tracking-wide text-text-muted">{plan.name}</div>
      <div className="mt-2 flex items-baseline gap-1">
        <span className="text-3xl font-bold tabular-nums text-text">{formatPrice(plan.price_cents)}</span>
        <span className="text-xs text-text-faint">per {plan.billing_interval === "WEEKLY" ? "week" : "month"}</span>
      </div>
      <div className="mt-2 text-xs font-medium text-green">{plan.trial_days}-Day Free Trial</div>
      <div className="mt-6">
        <Link href={`/subscribe?plan=${plan.id}`} className={CTA_LINK_CLASS}>
          Start Free Trial
        </Link>
      </div>
    </div>
  );
}

export default async function PricingPage() {
  const plans = await listActivePlans();

  return (
    <div className="min-h-screen bg-bg">
      <header className="border-b border-border bg-bg-panel px-6 py-4">
        <Link href="/" className="text-sm font-semibold tracking-tight text-text">
          BIG MONEY <span className="text-gold">DFS</span>
        </Link>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-16 text-center">
        <div className="mb-4 flex justify-center">
          <StripeTestModeBadge />
        </div>
        <h1 className="text-3xl font-bold leading-tight tracking-tight text-text sm:text-4xl">
          PLAY SMARTER.
          <br />
          BUILD BETTER LINEUPS.
        </h1>
        <p className="mx-auto mt-4 max-w-lg text-sm text-text-muted">
          AI-driven MLB DFS research, ownership projections, and lineup optimization -- built to find leverage the
          field is missing.
        </p>

        <div className="mx-auto mt-12 grid max-w-xl grid-cols-1 gap-6 sm:grid-cols-2">
          {plans.map((plan) => (
            <PlanCard key={plan.id} plan={plan} bestValue={plan.billing_interval === "MONTHLY"} />
          ))}
        </div>

        <p className="mx-auto mt-10 max-w-md text-xs text-text-faint">
          Recurring subscription. Cancel anytime. Billing begins after your {plans[0]?.trial_days ?? 3}-day trial
          unless canceled before the trial ends.
        </p>
      </main>
    </div>
  );
}
