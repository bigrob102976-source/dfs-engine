import { MetricCard } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Header";
import { computeAdminOverviewStats } from "@/lib/admin/overviewStats";

export const dynamic = "force-dynamic";

function fmtUsd(cents: number): string {
  return `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPct(value: number | null): string {
  return value === null ? "--" : `${value.toFixed(1)}%`;
}

export default async function AdminOverviewPage() {
  const stats = await computeAdminOverviewStats();

  return (
    <div>
      <PageHeader
        title="Admin Overview"
        description="Real-time membership and revenue figures derived from local data. No payment processor is connected -- MRR/ARR reflect the dev billing simulation only."
      />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
        <MetricCard label="Total Users" value={stats.totalUsers} />
        <MetricCard label="Active Members" value={stats.activeMembers} tone="positive" />
        <MetricCard label="Active Trials" value={stats.activeTrials} />
        <MetricCard label="Weekly Members" value={stats.weeklyMembers} />
        <MetricCard label="Monthly Members" value={stats.monthlyMembers} />
        <MetricCard label="Canceled Members" value={stats.canceledMembers} tone="negative" />
        <MetricCard label="Past Due" value={stats.pastDue} tone="negative" />
        <MetricCard label="Complimentary Accounts" value={stats.complimentaryAccounts} />
        <MetricCard label="MRR" value={fmtUsd(stats.mrrCents)} tone="positive" />
        <MetricCard label="Estimated ARR" value={fmtUsd(stats.arrCents)} tone="positive" />
        <MetricCard label="Trial Conversion" value={fmtPct(stats.trialConversionRatePct)} />
      </div>
    </div>
  );
}
