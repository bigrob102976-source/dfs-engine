import Link from "next/link";

import { UsersFilterBar } from "@/components/admin/UsersFilterBar";
import { PageHeader } from "@/components/ui/Header";
import { countAdminUsers, listAdminUsers } from "@/lib/db/adminUsers";

export const dynamic = "force-dynamic";

function fmtDate(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "--" : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function statusToneClass(status: string | null): string {
  if (!status) return "text-text-faint";
  if (status === "active" || status === "complimentary") return "text-green";
  if (status === "trialing") return "text-yellow";
  if (status === "past_due" || status === "canceled" || status === "expired") return "text-red";
  return "text-text-faint";
}

function firstParam(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) return value[0] ?? null;
  return value ?? null;
}

export default async function AdminUsersPage(props: PageProps<"/admin/users">) {
  const params = await props.searchParams;
  const filter = {
    search: firstParam(params.search),
    role: firstParam(params.role),
    subscriptionStatus: firstParam(params.subscriptionStatus),
    trialStatus: firstParam(params.trialStatus),
    betaAccess: firstParam(params.betaAccess),
    limit: 50,
  };

  const [users, total] = await Promise.all([listAdminUsers(filter), countAdminUsers(filter)]);

  return (
    <div>
      <PageHeader title="Users" description={`${total} user${total === 1 ? "" : "s"} total.`} />
      <UsersFilterBar />

      <div className="overflow-x-auto rounded-[var(--radius-card)] border border-border bg-bg-panel">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-border text-[10px] uppercase tracking-wide text-text-faint">
              <th className="px-3 py-2 font-medium">Email</th>
              <th className="px-3 py-2 font-medium">Role</th>
              <th className="px-3 py-2 font-medium">Plan</th>
              <th className="px-3 py-2 font-medium">Subscription Status</th>
              <th className="px-3 py-2 font-medium">Trial Ends</th>
              <th className="px-3 py-2 font-medium">Beta Access</th>
              <th className="px-3 py-2 font-medium">Joined</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b border-border-subtle last:border-0 hover:bg-bg-panel-raised">
                <td className="px-3 py-2">
                  <Link href={`/admin/users/${u.id}`} className="text-accent hover:text-accent-hover">
                    {u.email}
                  </Link>
                  {u.disabled_at && <span className="ml-2 rounded-full bg-red/15 px-2 py-0.5 text-[10px] text-red">Disabled</span>}
                </td>
                <td className="px-3 py-2 text-text">{u.role}</td>
                <td className="px-3 py-2 text-text-muted">{u.plan_name ?? "--"}</td>
                <td className={`px-3 py-2 font-medium ${statusToneClass(u.subscription_status)}`}>{u.subscription_status ?? "No subscription"}</td>
                <td className="px-3 py-2 text-text-muted">{fmtDate(u.trial_ends_at)}</td>
                <td className={`px-3 py-2 font-medium ${u.beta_access_granted_at ? "text-green" : "text-text-faint"}`}>
                  {u.beta_access_granted_at ? "Granted" : "--"}
                </td>
                <td className="px-3 py-2 text-text-muted">{fmtDate(u.created_at)}</td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-text-faint">
                  No users match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
