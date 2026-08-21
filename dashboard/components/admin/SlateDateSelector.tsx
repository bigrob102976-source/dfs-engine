"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

interface DiscoveredDate {
  date: string;
  slateCount: number;
  salaryCapSlateCount: number;
  hasUsableSlate: boolean;
  bestSlateId: string | null;
  bestSlateLabel: string | null;
  bestGameCount: number | null;
}

interface AvailableDatesResponse {
  status: string;
  providerName: string | null;
  today: string;
  smartDefaultDate: string;
  dates: DiscoveredDate[];
}

function fmtChip(d: DiscoveredDate, today: string): string {
  const label = d.bestSlateLabel ?? "slate";
  const suffix = d.bestGameCount != null ? ` -- ${label}, ${d.bestGameCount}g` : "";
  return `${d.date}${d.date === today ? " (today)" : ""}${suffix}`;
}

/** Milestone 31.2C, Part 4/5/7: lets an admin pick which calendar date's
 * slates to browse on /admin/slates, instead of always being locked to
 * Chicago-today -- DraftKings' own live lobby can roll to the next
 * calendar day before Chicago midnight (see lib/slateDate.ts's module
 * docstring). Selecting a date navigates to `${basePath}?date=...` (Part
 * 7's "persist selected date in navigation" -- a page refresh keeps the
 * same date). Quick-pick chips come from
 * /api/admin/slates/available-dates (admin-only; meaningless/skipped
 * for non-DK-unofficial provider configurations, in which case this
 * renders just the plain date input, no chips, no extra network noise). */
export function SlateDateSelector({ date, basePath }: { date: string; basePath: string }) {
  const router = useRouter();
  const [discovered, setDiscovered] = useState<AvailableDatesResponse | null>(null);
  const [inputValue, setInputValue] = useState(date);

  useEffect(() => {
    Promise.resolve().then(() => setInputValue(date));
  }, [date]);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/admin/slates/available-dates")
      .then((res) => res.json())
      .then((body) => {
        if (!cancelled) setDiscovered(body);
      })
      .catch(() => {
        /* Quick-pick chips are a convenience only -- the plain date input below always still works. */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function goTo(nextDate: string) {
    if (nextDate === date) return;
    router.push(`${basePath}?date=${encodeURIComponent(nextDate)}`);
  }

  const usableDates = discovered?.dates.filter((d) => d.hasUsableSlate) ?? [];

  return (
    <div className="mb-4 flex flex-wrap items-center gap-2 rounded-[var(--radius-card)] border border-border bg-bg-panel p-3 shadow-[var(--shadow-card)]">
      <label className="flex items-center gap-2 text-xs text-text-muted">
        Slate Date
        <input
          type="date"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onBlur={() => inputValue && goTo(inputValue)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && inputValue) goTo(inputValue);
          }}
          className="rounded border border-border bg-bg-panel-raised px-2 py-1 text-text"
        />
      </label>

      {discovered?.smartDefaultDate && discovered.smartDefaultDate !== date && (
        <button
          type="button"
          onClick={() => goTo(discovered.smartDefaultDate)}
          className="rounded bg-accent-dim px-2 py-1 text-[11px] font-medium text-text hover:opacity-80"
          title="DraftKings' current live lobby date with a usable Classic slate"
        >
          Jump to {discovered.smartDefaultDate}
        </button>
      )}

      {usableDates.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] uppercase tracking-wide text-text-faint">Available DK Dates</span>
          {usableDates.map((d) => (
            <button
              key={d.date}
              type="button"
              onClick={() => goTo(d.date)}
              disabled={d.date === date}
              title={`${d.salaryCapSlateCount} SalaryCap slate(s) of ${d.slateCount} discovered`}
              className={`rounded px-2 py-1 text-[11px] font-medium ${
                d.date === date ? "bg-green/15 text-green" : "bg-bg-panel-raised text-text-faint hover:text-text-muted"
              }`}
            >
              {fmtChip(d, discovered!.today)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
