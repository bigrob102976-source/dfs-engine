"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { SearchInput } from "@/components/ui/SearchInput";

const SELECT_CLASS =
  "rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-2.5 py-1.5 text-xs text-text outline-none focus:border-accent";

const STATUS_OPTIONS = [
  { value: "", label: "All" },
  { value: "trialing", label: "Trialing" },
  { value: "active", label: "Active" },
  { value: "past_due", label: "Past Due" },
  { value: "canceled", label: "Canceled" },
  { value: "expired", label: "Expired" },
  { value: "complimentary", label: "Complimentary" },
];

export function SubscriptionsFilterBar() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [search, setSearch] = useState(searchParams.get("search") ?? "");

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    router.push(`/admin/subscriptions?${next.toString()}`);
  }

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          updateParam("search", search);
        }}
      >
        <SearchInput value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search email or name..." className="w-56" />
      </form>
      <select className={SELECT_CLASS} value={searchParams.get("status") ?? ""} onChange={(e) => updateParam("status", e.target.value)}>
        {STATUS_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}
