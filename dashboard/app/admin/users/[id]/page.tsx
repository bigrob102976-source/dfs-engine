import { notFound } from "next/navigation";

import { ResyncSubscriptionButton } from "@/components/admin/ResyncSubscriptionButton";
import { RevokeEntitlementButton, UserAdminActions } from "@/components/admin/UserAdminActions";
import { TagBadge } from "@/components/ui/Badge";
import { DataCard } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Header";
import { listAuditLog } from "@/lib/db/auditLog";
import { listEntitlementsCatalog, listUserEntitlements } from "@/lib/db/entitlements";
import { listActivePlans } from "@/lib/db/plans";
import { getCurrentSubscriptionForUser } from "@/lib/db/subscriptions";
import { findUserById } from "@/lib/db/users";

export const dynamic = "force-dynamic";

function fmtDateTime(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "--" : d.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export default async function AdminUserDetailPage(props: PageProps<"/admin/users/[id]">) {
  const { id } = await props.params;
  const user = findUserById(id);
  if (!user) notFound();

  const subscription = getCurrentSubscriptionForUser(id);
  const entitlements = listUserEntitlements(id);
  const entitlementsCatalog = listEntitlementsCatalog();
  const plans = listActivePlans();
  const recentActivity = listAuditLog({ targetId: id, limit: 20 });

  return (
    <div>
      <PageHeader title={user.email} description={`User since ${fmtDateTime(user.created_at)}`} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="flex flex-col gap-4 lg:col-span-2">
          <DataCard title="Account">
            <dl className="grid grid-cols-2 gap-y-2 text-xs">
              <dt className="text-text-faint">Name</dt>
              <dd className="text-right text-text">{user.display_name ?? "--"}</dd>
              <dt className="text-text-faint">Email</dt>
              <dd className="text-right text-text">{user.email}</dd>
              <dt className="text-text-faint">Role</dt>
              <dd className="text-right text-text">{user.role}</dd>
              <dt className="text-text-faint">Email Verified</dt>
              <dd className="text-right text-text">{user.email_verified_at ? fmtDateTime(user.email_verified_at) : "Not verified"}</dd>
              <dt className="text-text-faint">Status</dt>
              <dd className="text-right">
                {user.disabled_at ? <span className="text-red">Disabled {fmtDateTime(user.disabled_at)}</span> : <span className="text-green">Active</span>}
              </dd>
            </dl>
          </DataCard>

          <DataCard title="Subscription &amp; Billing">
            <dl className="grid grid-cols-2 gap-y-2 text-xs">
              <dt className="text-text-faint">Trial Eligibility</dt>
              <dd className="text-right text-text">{user.trial_consumed_at ? "Consumed" : "Eligible"}</dd>
              <dt className="text-text-faint">Trial Used</dt>
              <dd className="text-right text-text">{user.trial_consumed_at ? fmtDateTime(user.trial_consumed_at) : "No"}</dd>
              <dt className="text-text-faint">Stripe Customer ID</dt>
              <dd className="text-right font-mono text-[11px] text-text">{user.stripe_customer_id ?? "--"}</dd>
            </dl>
            {subscription ? (
              <>
                <dl className="mt-3 grid grid-cols-2 gap-y-2 border-t border-border-subtle pt-3 text-xs">
                  <dt className="text-text-faint">Plan</dt>
                  <dd className="text-right text-text">{subscription.plan_id}</dd>
                  <dt className="text-text-faint">Billing Status</dt>
                  <dd className="text-right text-text">{subscription.status}</dd>
                  <dt className="text-text-faint">Billing Provider</dt>
                  <dd className="text-right text-text">{subscription.provider}</dd>
                  <dt className="text-text-faint">Stripe Subscription ID</dt>
                  <dd className="text-right font-mono text-[11px] text-text">{subscription.provider_subscription_id ?? "--"}</dd>
                  <dt className="text-text-faint">Trial Ends</dt>
                  <dd className="text-right text-text">{fmtDateTime(subscription.trial_ends_at)}</dd>
                  <dt className="text-text-faint">Current Period End</dt>
                  <dd className="text-right text-text">{fmtDateTime(subscription.current_period_end)}</dd>
                  <dt className="text-text-faint">Cancel At Period End</dt>
                  <dd className="text-right text-text">{subscription.cancel_at_period_end ? "Yes" : "No"}</dd>
                </dl>
                {subscription.provider === "stripe" && (
                  <div className="mt-3">
                    <ResyncSubscriptionButton subscriptionId={subscription.id} />
                  </div>
                )}
              </>
            ) : (
              <p className="mt-3 border-t border-border-subtle pt-3 text-xs text-text-faint">No subscription.</p>
            )}
          </DataCard>

          <DataCard title="Entitlements">
            {entitlements.length === 0 ? (
              <p className="text-xs text-text-faint">No explicit entitlement grants (plan/subscription access, if any, still applies separately).</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {entitlements.map((e) => (
                  <li key={e.entitlement_key} className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-2">
                      <TagBadge>{e.entitlement_key}</TagBadge>
                      {e.reason && <span className="text-text-faint">{e.reason}</span>}
                    </span>
                    <RevokeEntitlementButton userId={user.id} entitlementKey={e.entitlement_key} label={e.entitlement_key} />
                  </li>
                ))}
              </ul>
            )}
          </DataCard>

          <DataCard title="Recent Activity">
            {recentActivity.length === 0 ? (
              <p className="text-xs text-text-faint">No admin actions recorded for this user.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {recentActivity.map((entry) => (
                  <li key={entry.id} className="text-xs text-text-muted">
                    <span className="text-text-faint">{fmtDateTime(entry.created_at)}</span> -- {entry.action} by {entry.actor_label}
                  </li>
                ))}
              </ul>
            )}
          </DataCard>
        </div>

        <DataCard title="Administrative Actions">
          <UserAdminActions
            userId={user.id}
            role={user.role}
            disabled={Boolean(user.disabled_at)}
            hasComplimentary={subscription?.status === "complimentary"}
            hasSubscription={subscription !== null}
            plans={plans}
            entitlementsCatalog={entitlementsCatalog}
          />
        </DataCard>
      </div>
    </div>
  );
}
