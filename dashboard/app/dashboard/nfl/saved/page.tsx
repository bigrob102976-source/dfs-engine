"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { DangerButton, PrimaryButton, SecondaryButton } from "@/components/ui";
import { NflPageShell } from "@/components/nfl/NflPageShell";
import { fmtSalary } from "@/lib/nfl/format";
import type { NflSavedLineup } from "@/lib/nfl/types";
import { useNflDraftGroupId } from "@/lib/nfl/useNflDraftGroupId";

function SavedLineupsContent() {
  const draftGroupId = useNflDraftGroupId();
  const [lineups, setLineups] = useState<NflSavedLineup[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    try {
      const res = await fetch(`/api/nfl/lineups?draftGroupId=${draftGroupId}`);
      const json = await res.json();
      if (!res.ok) {
        setError(json.error || "Failed to load saved lineups.");
        return;
      }
      setLineups(json.lineups);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error loading saved lineups.");
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftGroupId]);

  async function deleteLineup(id: string) {
    setBusyId(id);
    try {
      const res = await fetch(`/api/nfl/lineups/${id}`, { method: "DELETE" });
      if (res.ok) await refresh();
    } finally {
      setBusyId(null);
    }
  }

  async function exportOne(id: string) {
    setBusyId(id);
    try {
      const res = await fetch("/api/nfl/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lineupIds: [id] }),
      });
      const json = await res.json();
      if (!res.ok || json.error) {
        setError(json.error || "Export failed.");
        return;
      }
      // Displayed inline for review -- the sandboxed viewer/local dev
      // context here never triggers a script-driven file download, so
      // the CSV text is shown for copy/paste rather than an <a download>.
      setError(null);
      window.alert(json.csv);
    } finally {
      setBusyId(null);
    }
  }

  if (error) return <p className="text-sm text-red">{error}</p>;
  if (lineups === null) return <p className="text-sm text-text-faint">Loading saved lineups…</p>;
  if (lineups.length === 0) {
    return (
      <p className="text-sm text-text-faint">
        No saved lineups yet for this slate. Build lineups on the Optimizer tab, then Save Lineup on the Lineups tab.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-text-faint">
        Real per-game lock state (nfl/game_lock.py) is computed fresh every time you open Late Swap -- never a stale cached value.
      </p>
      <div className="overflow-x-auto rounded-[var(--radius-card)] border border-border">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-border-subtle bg-bg-panel-raised text-text-faint">
              <th className="px-2 py-2">Saved</th>
              <th className="px-2 py-2">Mode</th>
              <th className="px-2 py-2">QB</th>
              <th className="px-2 py-2">Salary</th>
              <th className="px-2 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {lineups.map((lu) => {
              const qb = lu.slots.find((s) => s.roster_slot === "QB");
              const totalSalary = lu.slots.reduce((sum, s) => sum + s.salary, 0);
              return (
                <tr key={lu.id} className="border-b border-border-subtle/50">
                  <td className="px-2 py-1.5 text-text-muted">{new Date(lu.updated_at).toLocaleString()}</td>
                  <td className="px-2 py-1.5 text-text-muted">{lu.mode}</td>
                  <td className="px-2 py-1.5 font-medium text-text">{qb?.name ?? "--"}</td>
                  <td className="px-2 py-1.5 text-text-muted">{fmtSalary(totalSalary)}</td>
                  <td className="px-2 py-1.5">
                    <div className="flex gap-1.5">
                      <Link href={`/dashboard/nfl/saved/${lu.id}?draftGroupId=${draftGroupId}`}>
                        <PrimaryButton className="px-2 py-0.5 text-[11px]">Late Swap</PrimaryButton>
                      </Link>
                      <SecondaryButton onClick={() => exportOne(lu.id)} disabled={busyId === lu.id} className="px-2 py-0.5 text-[11px]">
                        Export
                      </SecondaryButton>
                      <DangerButton onClick={() => deleteLineup(lu.id)} disabled={busyId === lu.id} className="px-2 py-0.5 text-[11px]">
                        Delete
                      </DangerButton>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function NflSavedLineupsPage() {
  return (
    <NflPageShell
      title="NFL Saved Lineups / Late Swap"
      description="Save a lineup here, then run Late Swap once real games start locking -- locked players are never altered."
    >
      <SavedLineupsContent />
    </NflPageShell>
  );
}
