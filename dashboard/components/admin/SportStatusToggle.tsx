"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const SELECT_CLASS =
  "rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-2.5 py-1.5 text-xs font-medium outline-none focus:border-accent";

export function SportStatusToggle({ code, status }: { code: string; status: "LIVE" | "COMING_SOON" }) {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);

  async function handleChange(next: string) {
    setSubmitting(true);
    await fetch(`/api/admin/sports/${code}/status`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ status: next }),
    });
    setSubmitting(false);
    router.refresh();
  }

  return (
    <select
      value={status}
      disabled={submitting}
      onChange={(e) => handleChange(e.target.value)}
      className={`${SELECT_CLASS} ${status === "LIVE" ? "text-green" : "text-text-faint"}`}
    >
      <option value="LIVE">LIVE</option>
      <option value="COMING_SOON">Coming Soon</option>
    </select>
  );
}
