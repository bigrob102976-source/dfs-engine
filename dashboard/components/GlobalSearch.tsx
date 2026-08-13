"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { filterSearchIndex, type SearchIndexEntry } from "@/lib/search";

function Flag({ on, label }: { on: boolean; label: string }) {
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] ${on ? "bg-accent-dim text-text" : "text-text-faint"}`}>
      {label}
    </span>
  );
}

export function GlobalSearch({ index }: { index: SearchIndexEntry[] }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const results = useMemo(() => filterSearchIndex(index, query).slice(0, 20), [index, query]);

  return (
    <div className="relative w-80">
      <input
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder="Search any player..."
        className="w-full rounded border border-border bg-bg-panel-raised px-3 py-1.5 text-sm text-text outline-none placeholder:text-text-faint focus:border-accent"
      />
      {open && query.trim() && (
        <div className="absolute z-20 mt-1 max-h-96 w-full overflow-y-auto rounded border border-border bg-bg-panel shadow-xl">
          {results.length === 0 ? (
            <div className="p-3 text-xs text-text-faint">No players match &quot;{query}&quot;.</div>
          ) : (
            results.map((r) => {
              const target = r.playerType === "pitcher" ? "/dashboard/pitchers" : "/dashboard/hitters";
              return (
                <Link
                  key={r.id}
                  href={`${target}?player=${encodeURIComponent(r.id)}`}
                  className="flex items-center justify-between gap-2 border-b border-border-subtle px-3 py-2 last:border-b-0 hover:bg-bg-panel-raised"
                >
                  <span className="flex flex-col">
                    <span className="text-sm text-text">{r.name}</span>
                    <span className="text-[11px] text-text-faint">
                      {r.team} &middot; {r.playerType}
                    </span>
                  </span>
                  <span className="flex gap-1">
                    <Flag on={r.inPitcherSnapshot || r.inBatterSnapshot} label="snapshot" />
                    <Flag on={r.inOwnership} label="own" />
                    <Flag on={r.optimizerLineupCount > 0} label={`opt ${r.optimizerLineupCount || ""}`.trim()} />
                    <Flag on={r.inYesterdayEvaluation} label="eval" />
                  </span>
                </Link>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
