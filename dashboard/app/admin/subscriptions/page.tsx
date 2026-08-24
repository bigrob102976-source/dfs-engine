import Link from "next/link";

import { SubscriptionsFilterBar } from "@/components/admin/SubscriptionsFilterBar";
import { PageHeader } from "@/components/ui/Header";
import { listSubscriptions } from "@/lib/db/subscriptions";
import type { SubscriptionStatus } from "@/lib/db/types";

export const dynamic = "force-dynamic";

const VALID_STATUSES: SubscriptionStatus[] = ["trialing", "active", "past_due", "canceled", "expired", "complimentary"];

function fmtDate(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "--" : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function fmtPrice(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function statusToneClass(status: SubscriptionStatus): string {
  if (status === "active" || status === "complimentary") return "text-green";
  if (status === "trialing") return "text-yellow";
  return "text-red";
}

function firstParam(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) return value[0] ?? null;
  return value ?? null;
}

/** Stripe object IDs (customer/subscription) are safe to display -- they
 * are not secrets, unlike API keys. Never render process.env.STRIPE_*
 * here. */
function idOrDash(id: string | null): string {
  return id ?? "--";
}

export default async function AdminSubscriptionsPage(props: PageProps<"/admin/subscriptions">) {
  const params = await props.searchParams;
  const statusParam = firstParam(params.status);
  const status = statusParam && (VALID_STATUSES as string[]).includes(statusParam) ? (statusParam as SubscriptionStatus) : null;

  const subscriptions = await listSubscriptions({ status, search: firstParam(params.search), limit: 100 });

  return (
    <div>
      <PageHeader title="Subscriptions" description={`${subscriptions.length} subscription${subscriptions.length === 1 ? "" : "s"} shown.`} />
      <SubscriptionsFilterBar />

      <div className="overflow-x-auto rounded-[var(--radius-card)] border border-border bg-bg-panel">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-border text-[10px] uppercase tracking-wide text-text-faint">
              <th className="px-3 py-2 font-medium">User</th>
              <th className="px-3 py-2 font-medium">Plan</th>
              <th className="px-3 py-2 font-medium">Price</th>
              <th className="px-3 py-2 font-medium">Provider</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Trial End</th>
              <th className="px-3 py-2 font-medium">Next Billing</th>
              <th className="px-3 py-2 font-medium">Cancel At Period End</th>
              <th className="px-3 py-2 font-medium">Stripe Customer ID</th>
              <th className="px-3 py-2 font-medium">Stripe Subscription ID</th>
              <th className="px-3 py-2 font-medium">Created</th>
            </tr>
          </thead>
          <tbody>
            {subscriptions.map((s) => (
              <tr key={s.id} className="border-b border-border-subtle last:border-0 hover:bg-bg-panel-raised">
                <td className="px-3 py-2">
                  <Link href={`/admin/users/${s.user_id}`} className="text-accent hover:text-accent-hover">
                    {s.user_email}
                  </Link>
                </td>
                <td className="px-3 py-2 text-text-muted">{s.plan_name}</td>
                <td className="px-3 py-2 text-text-muted">{fmtPrice(s.plan_price_cents)}</td>
                <td className="px-3 py-2 text-text-muted">{s.provider}</td>
                <td className={`px-3 py-2 font-medium ${statusToneClass(s.status)}`}>{s.status}</td>
                <td className="px-3 py-2 text-text-muted">{fmtDate(s.trial_ends_at)}</td>
                <td className="px-3 py-2 text-text-muted">{fmtDate(s.current_period_end)}</td>
                <td className="px-3 py-2 text-text-muted">{s.cancel_at_period_end ? "Yes" : "No"}</td>
                <td className="px-3 py-2 font-mono text-[11px] text-text-faint">{idOrDash(s.user_stripe_customer_id)}</td>
                <td className="px-3 py-2 font-mono text-[11px] text-text-faint">{idOrDash(s.provider_subscription_id)}</td>
                <td className="px-3 py-2 text-text-muted">{fmtDate(s.created_at)}</td>
              </tr>
            ))}
            {subscriptions.length === 0 && (
              <tr>
                <td colSpan={11} className="px-3 py-6 text-center text-text-faint">
                  No subscriptions match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
