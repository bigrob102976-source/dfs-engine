"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const SELECT_CLASS =
  "rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-2.5 py-1.5 text-xs font-medium outline-none focus:border-accent";

const STATE_TONE: Record<string, string> = {
  PRODUCTION: "text-green",
  BETA: "text-yellow",
  ADMIN_ONLY: "text-accent",
  DISABLED: "text-red",
};

export function FeatureFlagSelect({ flagKey, state }: { flagKey: string; state: string }) {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);

  async function handleChange(next: string) {
    setSubmitting(true);
    await fetch(`/api/admin/features/${encodeURIComponent(flagKey)}/state`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ state: next }),
    });
    setSubmitting(false);
    router.refresh();
  }

  return (
    <select
      value={state}
      disabled={submitting}
      onChange={(e) => handleChange(e.target.value)}
      className={`${SELECT_CLASS} ${STATE_TONE[state] ?? "text-text"}`}
    >
      <option value="PRODUCTION">Production</option>
      <option value="BETA">Beta</option>
      <option value="ADMIN_ONLY">Admin Only</option>
      <option value="DISABLED">Disabled</option>
    </select>
  );
}
