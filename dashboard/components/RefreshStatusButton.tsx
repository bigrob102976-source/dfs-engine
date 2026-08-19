"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { SecondaryButton } from "@/components/ui/Button";

// Milestone 30.1: member-facing "Refresh status" -- re-fetches this
// already-published page's data via a Server Component re-render. Never
// triggers the backend pipeline (Process/Refresh Data are admin-only
// actions on /admin/slates) -- this only re-reads whatever the admin has
// already published.
export function RefreshStatusButton() {
  const router = useRouter();
  const [refreshing, setRefreshing] = useState(false);

  return (
    <SecondaryButton
      type="button"
      disabled={refreshing}
      onClick={() => {
        setRefreshing(true);
        router.refresh();
        setTimeout(() => setRefreshing(false), 600);
      }}
    >
      {refreshing ? "Refreshing..." : "Refresh status"}
    </SecondaryButton>
  );
}
