import Link from "next/link";

import { CancelButton } from "@/components/auth/BillingActions";
import { ManageSubscriptionButton } from "@/components/billing/ManageSubscriptionButton";
import { TagBadge } from "@/components/ui/Badge";
import { DataCard } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Header";
import { requireAuth } from "@/lib/auth/guards";
import { getBillingMode, type BillingMode } from "@/lib/billing/stripeConfig";
import { getPlan } from "@/lib/db/plans";
import { getCurrentSubscriptionForUser } from "@/lib/db/subscriptions";

export const dynamic = "force-dynamic";

const ACCESS_GRANTING_STATUSES = new Set(["trialing", "active", "complimentary"]);

function fmtDate(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "--" : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function billingModeLabel(mode: BillingMode): string {
  if (mode === "stripe_test") return "Stripe (Test Mode)";
  if (mode === "dev") return "Development Mode (simulated)";
  return "Not Configured";
}

export default async function BillingPage() {
  const user = await requireAuth();
  const subscription = getCurrentSubscriptionForUser(user.id);
  const plan = subscription ? getPlan(subscription.plan_id) : null;
  const billingMode = getBillingMode();
  const hasAccess = subscription !== null && ACCESS_GRANTING_STATUSES.has(subscription.status);
  const accessThrough = subscription ? (subscription.status === "trialing" ? subscription.trial_ends_at : subscription.current_period_end) : null;

  return (
    <div>
      <PageHeader title="Billing" description="Manage your Big Money DFS membership." />

      {billingMode !== "stripe_test" && (
        <div className="mb-4 rounded border border-yellow bg-bg-panel-raised p-3 text-xs text-yellow">
          <span className="font-semibold uppercase tracking-wide">
            {billingMode === "dev" ? "Development Mode" : "Billing Not Configured"}
          </span>
          {billingMode === "dev"
            ? " -- no real payment processor is connected yet. Subscribing simulates a trial locally; no card is collected and no charge occurs."
            : " -- Stripe is not configured yet. Please contact an administrator."}
        </div>
      )}

      {subscription ? (
        <DataCard title="Membership">
          <dl className="grid grid-cols-2 gap-y-2 text-xs">
            <dt className="text-text-faint">Plan</dt>
            <dd className="text-right text-text">{plan?.name ?? subscription.plan_id}</dd>
            <dt className="text-text-faint">Price</dt>
            <dd className="text-right text-text">
              {plan ? `$${(plan.price_cents / 100).toFixed(2)} / ${plan.billing_interval === "WEEKLY" ? "week" : "month"}` : "--"}
            </dd>
            <dt className="text-text-faint">Subscription Status</dt>
            <dd className="text-right">
              <TagBadge>{subscription.status}</TagBadge>
            </dd>
            <dt className="text-text-faint">Trial Status</dt>
            <dd className="text-right text-text">
              {subscription.status === "trialing" ? "In Trial" : subscription.trial_ends_at ? "Trial Used" : "N/A"}
            </dd>
            <dt className="text-text-faint">Trial End</dt>
            <dd className="text-right text-text">{fmtDate(subscription.trial_ends_at)}</dd>
            <dt className="text-text-faint">Next Billing Date</dt>
            <dd className="text-right text-text">{fmtDate(subscription.current_period_end)}</dd>
            <dt className="text-text-faint">Cancel at Period End</dt>
            <dd className="text-right text-text">{subscription.cancel_at_period_end ? "Yes" : "No"}</dd>
            <dt className="text-text-faint">Access Through</dt>
            <dd className="text-right text-text">{hasAccess ? fmtDate(accessThrough) : "--"}</dd>
            <dt className="text-text-faint">Billing Provider</dt>
            <dd className="text-right text-text">{billingModeLabel(billingMode)}</dd>
          </dl>
          <div className="mt-4 flex flex-wrap gap-2">
            <ManageSubscriptionButton />
            {hasAccess && <CancelButton />}
          </div>
        </DataCard>
      ) : (
        <DataCard title="No Active Membership">
          <p className="mb-3 text-xs text-text-faint">You don&apos;t have an active Big Money DFS membership yet.</p>
          <Link href="/pricing" className="text-sm text-accent hover:text-accent-hover">
            View plans →
          </Link>
        </DataCard>
      )}
    </div>
  );
}
