"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";

import { DEFAULT_NFL_DRAFT_GROUP_ID } from "@/lib/nfl/types";

interface RealNflSlate {
  draft_group_id: number;
  slate_date: string;
  start_time: string | null;
  tag: string | null;
  label: string | null;
}

/** NFL UI M1 -- real DraftKings NFL Classic slate selector (never
 * hardcoded to one DraftGroup; fetches the live discovery API). Updates
 * the current page's ?draftGroupId= query param so the selection is
 * shareable and carries across NflTabs navigation. */
export function NflSlateSelector() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const current = searchParams.get("draftGroupId") ?? String(DEFAULT_NFL_DRAFT_GROUP_ID);

  const [slates, setSlates] = useState<RealNflSlate[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/nfl/slates")
      .then(async (res) => {
        const json = await res.json();
        if (!res.ok || json.error) {
          setError(json.error || "Failed to load real NFL slates.");
          return;
        }
        setSlates(json.slates as RealNflSlate[]);
      })
      .catch(() => setError("Failed to load real NFL slates."));
  }, []);

  function onChange(value: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("draftGroupId", value);
    router.push(`${pathname}?${params.toString()}`);
  }

  if (error) {
    return <span className="text-xs text-red">{error}</span>;
  }

  if (!slates) {
    return <span className="text-xs text-text-faint">Loading real NFL Classic slates…</span>;
  }

  if (slates.length === 0) {
    return <span className="text-xs text-text-faint">No real NFL Classic slates currently posted.</span>;
  }

  return (
    <select
      value={current}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-2 py-1.5 text-xs text-text"
    >
      {slates.map((s) => (
        <option key={s.draft_group_id} value={s.draft_group_id}>
          {s.slate_date} · DraftGroup {s.draft_group_id}
          {s.tag ? ` · ${s.tag}` : ""}
          {s.label ? ` ${s.label}` : ""}
        </option>
      ))}
    </select>
  );
}
