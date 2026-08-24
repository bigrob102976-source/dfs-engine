import Link from "next/link";

import { requireAuth } from "@/lib/auth/guards";
import { TagBadge } from "@/components/ui/Badge";
import { DataCard } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Header";
import { getPlan } from "@/lib/db/plans";
import { listSports } from "@/lib/db/sports";
import { getCurrentSubscriptionForUser } from "@/lib/db/subscriptions";

export const dynamic = "force-dynamic";

function fmtDate(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "--" : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export default async function AccountPage() {
  const user = await requireAuth();
  const subscription = await getCurrentSubscriptionForUser(user.id);
  const plan = subscription ? await getPlan(subscription.plan_id) : null;
  const sports = await listSports();

  return (
    <div>
      <PageHeader title="Account" description="Your profile, membership, and sports access." />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <DataCard title="Profile">
          <dl className="grid grid-cols-2 gap-y-2 text-xs">
            <dt className="text-text-faint">Name</dt>
            <dd className="text-right text-text">{user.displayName ?? "--"}</dd>
            <dt className="text-text-faint">Email</dt>
            <dd className="text-right text-text">{user.email}</dd>
            <dt className="text-text-faint">Role</dt>
            <dd className="text-right text-text">{user.role}</dd>
          </dl>
        </DataCard>

        <DataCard
          title="Membership"
          action={
            <Link href="/account/billing" className="text-[11px] text-accent hover:text-accent-hover">
              Manage →
            </Link>
          }
        >
          {subscription ? (
            <dl className="grid grid-cols-2 gap-y-2 text-xs">
              <dt className="text-text-faint">Plan</dt>
              <dd className="text-right text-text">{plan?.name ?? "--"}</dd>
              <dt className="text-text-faint">Subscription Status</dt>
              <dd className="text-right">
                <TagBadge>{subscription.status}</TagBadge>
              </dd>
              <dt className="text-text-faint">Trial Ends</dt>
              <dd className="text-right text-text">{fmtDate(subscription.trial_ends_at)}</dd>
              <dt className="text-text-faint">Next Billing Date</dt>
              <dd className="text-right text-text">{fmtDate(subscription.current_period_end)}</dd>
            </dl>
          ) : (
            <p className="text-xs text-text-faint">
              No active membership.{" "}
              <Link href="/account/billing" className="text-accent hover:text-accent-hover">
                Choose a plan →
              </Link>
            </p>
          )}
        </DataCard>

        <DataCard title="Sports Access" className="md:col-span-2">
          <ul className="flex flex-wrap gap-2 text-xs">
            {sports.map((sport) => (
              <li
                key={sport.code}
                className={`rounded-full px-3 py-1 ${sport.status === "LIVE" ? "bg-green/15 text-green" : "bg-bg-panel-raised text-text-faint"}`}
              >
                {sport.name}
                {sport.status !== "LIVE" && " (Coming Soon)"}
              </li>
            ))}
          </ul>
        </DataCard>
      </div>
    </div>
  );
}
