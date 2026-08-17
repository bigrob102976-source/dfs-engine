"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { SearchInput } from "@/components/ui/SearchInput";

const SELECT_CLASS =
  "rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-2.5 py-1.5 text-xs text-text outline-none focus:border-accent";

const ROLE_OPTIONS = [
  { value: "", label: "All Roles" },
  { value: "MEMBER", label: "Member" },
  { value: "ADMIN", label: "Admin" },
];

const STATUS_OPTIONS = [
  { value: "", label: "All Statuses" },
  { value: "trialing", label: "Trialing" },
  { value: "active", label: "Active" },
  { value: "past_due", label: "Past Due" },
  { value: "canceled", label: "Canceled" },
  { value: "expired", label: "Expired" },
  { value: "complimentary", label: "Complimentary" },
  { value: "none", label: "No Subscription" },
];

const TRIAL_OPTIONS = [
  { value: "", label: "Any Trial Status" },
  { value: "in_trial", label: "In Trial" },
  { value: "trial_expired", label: "Trial Expired" },
];

/** Reads/writes filters as URL query params so the list is always
 * driven by a real server-rendered page.tsx (no client-side data
 * fetching duplication, filters are shareable/bookmarkable links). */
export function UsersFilterBar() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [search, setSearch] = useState(searchParams.get("search") ?? "");

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    router.push(`/admin/users?${next.toString()}`);
  }

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          updateParam("search", search);
        }}
      >
        <SearchInput
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search email or name..."
          className="w-56"
        />
      </form>
      <select className={SELECT_CLASS} value={searchParams.get("role") ?? ""} onChange={(e) => updateParam("role", e.target.value)}>
        {ROLE_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <select
        className={SELECT_CLASS}
        value={searchParams.get("subscriptionStatus") ?? ""}
        onChange={(e) => updateParam("subscriptionStatus", e.target.value)}
      >
        {STATUS_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <select
        className={SELECT_CLASS}
        value={searchParams.get("trialStatus") ?? ""}
        onChange={(e) => updateParam("trialStatus", e.target.value)}
      >
        {TRIAL_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}
