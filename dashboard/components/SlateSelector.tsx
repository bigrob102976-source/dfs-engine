"use client";

import { useState } from "react";

import type { SlateOption } from "@/lib/orchestrator/types";

/** Shown only when the configured DFS provider exposes more than one
 * relevant slate for today and the pipeline has paused, awaiting a
 * choice. The user picks in-app -- no CSV, no path typing. `onSelect`
 * only ever receives one of the ids in `options`, which the server
 * re-validates against the run's own discovered options before it's
 * ever passed to a Python subprocess. */
export function SlateSelector({
  options,
  onSelect,
  disabled,
}: {
  options: SlateOption[];
  onSelect: (slateId: string) => void;
  disabled?: boolean;
}) {
  const [selected, setSelected] = useState<string>(options[0]?.slateId ?? "");

  return (
    <div className="rounded border border-yellow bg-bg-panel-raised p-3">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-yellow">Multiple DFS slates found -- choose one</div>
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          disabled={disabled}
          className="rounded border border-border bg-bg-panel px-2 py-1.5 text-sm text-text"
        >
          {options.map((option) => (
            <option key={option.slateId} value={option.slateId}>
              {option.slateName ?? option.slateId}
              {option.startTime ? ` -- ${option.startTime}` : ""}
              {option.gameCount != null ? ` (${option.gameCount} games)` : ""}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => onSelect(selected)}
          disabled={disabled || !selected}
          className="rounded border border-accent bg-accent-dim px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-text disabled:cursor-not-allowed disabled:opacity-50"
        >
          Use this slate
        </button>
      </div>
    </div>
  );
}
