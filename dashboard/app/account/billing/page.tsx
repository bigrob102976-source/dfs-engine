import { CancelButton, SubscribeButton } from "@/components/auth/BillingActions";
import { DataCard } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Header";
import { requireAuth } from "@/lib/auth/guards";
import { listActivePlans } from "@/lib/db/plans";
import { getCurrentSubscriptionForUser } from "@/lib/db/subscriptions";

export const dynamic = "force-dynamic";

function formatPrice(cents: number, interval: "WEEKLY" | "MONTHLY"): string {
  const dollars = (cents / 100).toFixed(2);
  return `$${dollars} / ${interval === "WEEKLY" ? "week" : "month"}`;
}

export default async function BillingPage() {
  const user = await requireAuth();
  const plans = listActivePlans();
  const subscription = getCurrentSubscriptionForUser(user.id);
  const hasActiveMembership = subscription !== null && subscription.status !== "canceled" && subscription.status !== "expired";

  return (
    <div>
      <PageHeader title="Billing" description="Manage your Big Money DFS membership." />

      <div className="mb-4 rounded border border-yellow bg-bg-panel-raised p-3 text-xs text-yellow">
        <span className="font-semibold uppercase tracking-wide">Dev Mode</span> -- no real payment processor is
        connected yet. Starting a trial here simulates a subscription locally; no card is collected and no charge
        occurs. Real subscription checkout will be connected in a dedicated future milestone.
      </div>

      {hasActiveMembership && subscription ? (
        <DataCard title="Current Plan" className="mb-4">
          <p className="mb-3 text-sm text-text">
            You are <span className="font-semibold">{subscription.status}</span> on the plan you selected. Recurring
            billing applies at the end of your trial/period unless canceled.
          </p>
          <CancelButton />
        </DataCard>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {plans.map((plan) => (
            <DataCard key={plan.id} title={plan.name}>
              <div className="mb-3 text-2xl font-semibold text-text">{formatPrice(plan.price_cents, plan.billing_interval)}</div>
              <p className="mb-4 text-xs text-text-faint">{plan.trial_days}-day free trial, then recurring billing at this rate.</p>
              <SubscribeButton plan={plan} />
            </DataCard>
          ))}
        </div>
      )}
    </div>
  );
}
