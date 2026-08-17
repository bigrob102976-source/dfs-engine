import { MetricCard } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Header";
import { computeAdminRevenueStats } from "@/lib/admin/revenueStats";

export const dynamic = "force-dynamic";

function fmtUsd(cents: number): string {
  return `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPct(value: number | null): string {
  return value === null ? "--" : `${value.toFixed(1)}%`;
}

export default async function AdminRevenuePage() {
  const stats = computeAdminRevenueStats();

  return (
    <div>
      <PageHeader
        title="Revenue"
        description="No payment processor is connected -- every figure below is computed from real local subscription rows and the seeded plan catalog (dev billing simulation only), never fabricated."
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
        <MetricCard label="MRR" value={fmtUsd(stats.mrrCents)} tone="positive" />
        <MetricCard label="Estimated ARR" value={fmtUsd(stats.arrCents)} tone="positive" />
        <MetricCard label="Weekly Plan Revenue" value={fmtUsd(stats.weeklyRevenueCents)} />
        <MetricCard label="Monthly Plan Revenue" value={fmtUsd(stats.monthlyRevenueCents)} />
        <MetricCard label="Refunds" value="--" />
        <MetricCard label="New Subscribers (Month)" value={stats.newSubscribersThisMonth} />
        <MetricCard label="Active Trials" value={stats.activeTrials} />
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
