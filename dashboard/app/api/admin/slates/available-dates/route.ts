import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { getTodayEasternDate } from "@/lib/currentDate";
import { parseLastJsonLine } from "@/lib/optimizerWorkspace/jsonLine";
import { runPythonScript, tail } from "@/lib/orchestrator/pythonRunner";

export const dynamic = "force-dynamic";

interface DiscoveredDate {
  date: string;
  slateCount: number;
  salaryCapSlateCount: number;
  hasUsableSlate: boolean;
  bestSlateId: string | null;
  bestSlateLabel: string | null;
  bestGameCount: number | null;
}

/** Milestone 31.2C, Part 5/6: which nearby calendar dates the DK
 * unofficial development provider currently has usable Classic/
 * SalaryCap DraftGroups for (via scripts/discover_dk_slate_dates.py --
 * read-only, one extra network call, no extra DraftKings endpoint
 * beyond what the provider's own get_slate() already uses), plus the
 * "smart default" date/slate this milestone's Part 6 defines:
 *   1. Chicago-today if it has a usable SalaryCap slate.
 *   2. Otherwise the nearest FUTURE date that does.
 *   3. Otherwise Chicago-today anyway (normal empty-state behavior --
 *      the admin board just shows "no slates discovered yet").
 * Meaningless (and never called) for CSV/mock provider configurations
 * -- the script itself reports "not_applicable" with zero network
 * calls in that case, passed straight through here. */
export async function GET() {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const today = getTodayEasternDate();
  const result = await runPythonScript("scripts/discover_dk_slate_dates.py", ["--sport", "MLB"]);
  const doc = parseLastJsonLine(result.stdout);

  if (!doc || result.exitCode !== 0) {
    return NextResponse.json({
      status: "unavailable",
      reason: `Unexpected date-discovery failure: ${tail(result.stdout + result.stderr, 500)}`,
      today,
      smartDefaultDate: today,
      dates: [],
    });
  }

  const rawDates = Array.isArray(doc.dates) ? (doc.dates as Record<string, unknown>[]) : [];
  const dates: DiscoveredDate[] = rawDates.map((d) => ({
    date: String(d.date),
    slateCount: typeof d.slate_count === "number" ? d.slate_count : 0,
    salaryCapSlateCount: typeof d.salary_cap_slate_count === "number" ? d.salary_cap_slate_count : 0,
    hasUsableSlate: Boolean(d.has_usable_slate),
    bestSlateId: (d.best_slate_id as string | null) ?? null,
    bestSlateLabel: (d.best_slate_label as string | null) ?? null,
    bestGameCount: (d.best_game_count as number | null) ?? null,
  }));

  const byDate = new Map(dates.map((d) => [d.date, d]));
  const todayUsable = byDate.get(today)?.hasUsableSlate ?? false;
  const nextUsableFutureDate = dates.filter((d) => d.date > today && d.hasUsableSlate).sort((a, b) => a.date.localeCompare(b.date))[0]?.date ?? null;
  const smartDefaultDate = todayUsable ? today : (nextUsableFutureDate ?? today);

  return NextResponse.json({
    status: (doc.status as string) ?? "ok",
    reason: (doc.reason as string | null) ?? null,
    providerName: (doc.provider_name as string | null) ?? null,
    today,
    smartDefaultDate,
    dates,
  });
}
