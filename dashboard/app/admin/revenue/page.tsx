import { MetricCard } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Header";
import { computeAdminRevenueStats } from "@/lib/admin/revenueStats";
import { getBillingMode } from "@/lib/billing/stripeConfig";

export const dynamic = "force-dynamic";

function fmtUsd(cents: number): string {
  return `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPct(value: number | null): string {
  return value === null ? "--" : `${value.toFixed(1)}%`;
}

function billingDisclosure(mode: ReturnType<typeof getBillingMode>): string {
  if (mode === "stripe_test") {
    return "Stripe is connected in TEST MODE -- every figure below is computed from real synchronized subscription rows and the seeded plan catalog. No real charges have occurred.";
  }
  if (mode === "dev") {
    return "No payment processor is connected -- every figure below is computed from real local subscription rows and the seeded plan catalog (dev billing simulation only), never fabricated.";
  }
  return "Billing is not configured. Figures below reflect whatever subscription rows already exist locally.";
}

export default async function AdminRevenuePage() {
  const stats = await computeAdminRevenueStats();
  const billingMode = getBillingMode();

  return (
    <div>
      <PageHeader title="Revenue" description={billingDisclosure(billingMode)} />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
        <MetricCard label="MRR" value={fmtUsd(stats.mrrCents)} tone="positive" />
        <MetricCard label="Estimated ARR" value={fmtUsd(stats.arrCents)} tone="positive" />
        <MetricCard label="Weekly Plan Revenue" value={fmtUsd(stats.weeklyRevenueCents)} />
        <MetricCard label="Monthly Plan Revenue" value={fmtUsd(stats.monthlyRevenueCents)} />
        <MetricCard label="Active Subscribers" value={stats.activeSubscribers} tone="positive" />
        <MetricCard label="Weekly Subscribers" value={stats.weeklySubscribers} />
        <MetricCard label="Monthly Subscribers" value={stats.monthlySubscribers} />
        <MetricCard label="Trialing" value={stats.activeTrials} />
        <MetricCard label="Past Due" value={stats.pastDueSubscribers} tone="negative" />
        <MetricCard label="Canceled" value={stats.canceledSubscribers} tone="negative" />
        <MetricCard label="Refunds" value="--" />
        <MetricCard label="New Subscribers (Month)" value={stats.newSubscribersThisMonth} />
        <MetricCard label="Trial Conversion" value={fmtPct(stats.trialConversionRatePct)} />
        <MetricCard label="Cancellations (Month)" value={stats.cancellationsThisMonth} tone="negative" />
        <MetricCard label="Churn Rate" value="--" />
      </div>
      <p className="mt-4 text-xs text-text-faint">
        Refunds and Churn Rate show -- because this system does not yet track payment refunds or retain the
        point-in-time subscriber snapshots required to compute true churn -- not because the value is zero.
      </p>
    </div>
  );
}
