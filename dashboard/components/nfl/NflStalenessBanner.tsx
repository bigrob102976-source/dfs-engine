import type { NflSlateData } from "@/lib/nfl/types";

/** 2026-09-11 incident fix -- every NFL page that renders real player/
 * salary/status data now surfaces data_status honestly instead of
 * silently rendering a stale pool as current (nfl/pool_cache.py's
 * POOL_CACHE_STALE_MAX_SECONDS reuses a real pool up to 2 hours old
 * rather than attempting a live DraftKings call from production, which
 * is permanently blocked and previously surfaced as a bare 502 -- see
 * that module's own docstring). Same standard as the dashboard's Slate
 * Readiness card: absence/staleness is disclosed, never presented as
 * fresh. Renders nothing when data_status is "fresh". */
export function NflStalenessBanner({ data }: { data: Pick<NflSlateData, "data_status" | "pool_generated_at_utc"> }) {
  if (data.data_status !== "stale") return null;

  const ageLabel = (() => {
    if (!data.pool_generated_at_utc) return null;
    const generatedMs = Date.parse(data.pool_generated_at_utc);
    if (Number.isNaN(generatedMs)) return null;
    const minutes = Math.max(0, Math.round((Date.now() - generatedMs) / 60000));
    return minutes < 60 ? `${minutes} min ago` : `${Math.round(minutes / 60)}h ago`;
  })();

  return (
    <p role="status" className="rounded-[var(--radius-control)] border border-yellow/40 bg-yellow/10 p-2 text-xs text-yellow">
      ⚠ This data is stale{ageLabel ? ` (last refreshed ${ageLabel})` : ""} -- the automated DraftKings refresh has
      fallen behind. Salaries, injury status, and lineup news may not reflect the latest update.
    </p>
  );
}
