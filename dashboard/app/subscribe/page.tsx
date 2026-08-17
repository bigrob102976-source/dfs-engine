import Link from "next/link";

import { CheckoutButton } from "@/components/billing/CheckoutButton";
import { StripeTestModeBadge } from "@/components/billing/StripeTestModeBadge";
import { requireAuth } from "@/lib/auth/guards";
import { listActivePlans } from "@/lib/db/plans";
import { getCurrentSubscriptionForUser } from "@/lib/db/subscriptions";
import type { Plan } from "@/lib/db/types";

export const dynamic = "force-dynamic";

const ACCESS_GRANTING_STATUSES = new Set(["trialing", "active", "complimentary"]);

function formatPrice(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function firstParam(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) return value[0] ?? null;
  return value ?? null;
}

function PlanPickCard({ plan, preselected }: { plan: Plan; preselected: boolean }) {
  return (
    <div
      className={`flex flex-col rounded-[var(--radius-card)] border p-5 shadow-[var(--shadow-card)] ${
        preselected ? "border-accent bg-bg-panel" : "border-border bg-bg-panel"
      }`}
    >
      <div className="text-xs font-semibold uppercase tracking-wide text-text-muted">{plan.name}</div>
      <div className="mt-2 flex items-baseline gap-1">
        <span className="text-2xl font-bold tabular-nums text-text">{formatPrice(plan.price_cents)}</span>
        <span className="text-xs text-text-faint">/ {plan.billing_interval === "WEEKLY" ? "week" : "month"}</span>
      </div>
      <div className="mt-1 text-xs text-green">{plan.trial_days}-day free trial</div>
      <div className="mt-4">
        <CheckoutButton planId={plan.id} label="Continue to Secure Checkout" />
      </div>
    </div>
  );
}

export default async function SubscribePage(props: PageProps<"/subscribe">) {
  const params = await props.searchParams;
  const planParam = firstParam(params.plan);
  const nextPath = planParam ? `/subscribe?plan=${encodeURIComponent(planParam)}` : "/subscribe";

  const user = await requireAuth(nextPath);
  const subscription = getCurrentSubscriptionForUser(user.id);
  const alreadySubscribed = subscription !== null && ACCESS_GRANTING_STATUSES.has(subscription.status);

  if (alreadySubscribed) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <h1 className="text-lg font-semibold text-text">You&apos;re already a member</h1>
        <p className="mt-2 text-sm text-text-muted">Your Big Money DFS membership is active.</p>
        <Link href="/account/billing" className="mt-4 inline-block text-sm text-accent hover:text-accent-hover">
          Manage your membership →
        </Link>
      </div>
    );
  }

  const plans = listActivePlans();

  return (
    <div className="mx-auto max-w-2xl px-6 py-16">
      <div className="mb-6 flex justify-center">
        <StripeTestModeBadge />
      </div>
      <h1 className="text-center text-xl font-semibold text-text">Choose Your Plan</h1>
      <p className="mt-1 text-center text-xs text-text-faint">Cancel anytime. Billing starts after your free trial.</p>

      <div className="mt-8 grid grid-cols-1 gap-5 sm:grid-cols-2">
        {plans.map((plan) => (
          <PlanPickCard key={plan.id} plan={plan} preselected={plan.id === planParam} />
        ))}
      </div>
    </div>
  );
}
