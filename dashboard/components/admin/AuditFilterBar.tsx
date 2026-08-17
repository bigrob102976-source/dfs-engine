"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { SearchInput } from "@/components/ui/SearchInput";

/** Search-only -- audit actions are free-form strings (e.g.
 * user_role_changed, sport_status_changed), not a fixed enum, so no
 * dropdown of "every possible action" is maintained here. */
export function AuditFilterBar() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [search, setSearch] = useState(searchParams.get("search") ?? "");

  return (
    <form
      className="mb-3"
      onSubmit={(e) => {
        e.preventDefault();
        const next = new URLSearchParams(searchParams.toString());
        if (search) next.set("search", search);
        else next.delete("search");
        router.push(`/admin/audit?${next.toString()}`);
      }}
    >
      <SearchInput value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search actor, action, or target type..." className="w-72" />
    </form>
  );
}
