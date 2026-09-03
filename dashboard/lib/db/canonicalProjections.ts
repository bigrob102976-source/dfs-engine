import crypto from "node:crypto";

import { getNativeProjectionByPlayerId } from "../nativeProjections";
import { resolveMlbPlayerIds } from "./canonicalPlayerIdentity";
import { getExecutor } from "./executor";
import type { CanonicalSlatePlayerRow, CanonicalSlateRow } from "./types";

// MLB FINISH MODE Phase B -- the Big Money Native projection bridge.
// Mirrors canonicalEligibility.ts's own architecture exactly: the real
// model (native_projections/*.py, via scripts/run_native_projection_engine.py)
// is completely unchanged and untouched by this file -- it already
// produces an immutable, timestamped native_projection_snapshots/<date>/
// artifact keyed by MLB player id, entirely independent of which DK
// salary/roster source (legacy or canonical) is in use, since it reads
// only the research pitcher/batter boards (see that engine's own module
// docstring). This module's ONLY job is: read the already-computed
// snapshot for a slate's date, join it onto this canonical slate's real
// DK players by mlbPlayerId, and persist the result as this slate's
// CURRENT projection state -- never a second projection algorithm,
// never a fabricated value for a player the snapshot doesn't cover.
//
// A player is written here ONLY when BOTH (a) their identity resolved
// to a real mlbPlayerId and (b) the Native snapshot actually has an
// entry for that mlbPlayerId -- anyone else is simply absent from this
// table, which canonicalPostgresBackend.ts then honestly reads back as
// null (never 0, never fabricated) -- same "unresolved identity remains
// servable" contract every other canonical bridge in this codebase uses.

export interface ProjectionComputeResult {
  status: "OK" | "NO_SNAPSHOT" | "SLATE_NOT_FOUND";
  reason?: string;
  playersUpdated: number;
}

export interface ProjectionRefreshForDateResult {
  date: string;
  slatesFound: number;
  slatesUpdated: number;
  slatesFailed: number;
  perSlate: Array<{ internalSlateId: string; providerSlateId: string } & ProjectionComputeResult>;
}

const NATIVE_SOURCE = "native";

/** Recomputes Native projection CURRENT state for every real,
 * currently-VALID canonical slate on `date` -- mirrors
 * refreshCanonicalEligibilityForDate's own per-slate failure isolation
 * (one slate's problem is caught, reported, and never stops the rest;
 * never thrown to the caller). Deliberately does NOT itself invoke
 * scripts/run_native_projection_engine.py -- that is a DATE-level,
 * slate-independent step the caller (the automatic research/refresh
 * orchestration) runs ONCE per date, exactly like
 * scripts/build_research_package.py already is; running it once here
 * per-slate would be redundant, wasted work for a multi-slate date. */
export async function refreshCanonicalProjectionsForDate(date: string, sport: string = "MLB"): Promise<ProjectionRefreshForDateResult> {
  const db = getExecutor();
  const slates = await db.all<{ internal_slate_id: string; provider_slate_id: string }>(
    "SELECT internal_slate_id, provider_slate_id FROM slates WHERE sport = ? AND slate_date = ? AND validation_state = 'VALID'",
    [sport, date],
  );

  const perSlate: ProjectionRefreshForDateResult["perSlate"] = [];
  for (const slate of slates) {
    let result: ProjectionComputeResult;
    try {
      result = await computeAndPersistNativeProjectionsForSlate(slate.internal_slate_id);
    } catch (err) {
      result = { status: "NO_SNAPSHOT", reason: err instanceof Error ? err.message : String(err), playersUpdated: 0 };
    }
    perSlate.push({ internalSlateId: slate.internal_slate_id, providerSlateId: slate.provider_slate_id, ...result });
  }

  return {
    date,
    slatesFound: slates.length,
    slatesUpdated: perSlate.filter((s) => s.status === "OK").length,
    slatesFailed: perSlate.filter((s) => s.status !== "OK").length,
    perSlate,
  };
}

export async function computeAndPersistNativeProjectionsForSlate(internalSlateId: string): Promise<ProjectionComputeResult> {
  const db = getExecutor();
  const slate = await db.get<CanonicalSlateRow>("SELECT * FROM slates WHERE internal_slate_id = ?", [internalSlateId]);
  if (!slate) return { status: "SLATE_NOT_FOUND", playersUpdated: 0 };

  const nativeByMlbId = await getNativeProjectionByPlayerId(slate.slate_date);
  if (nativeByMlbId.size === 0) {
    // Honest absence -- the engine hasn't produced a snapshot for this
    // date yet (e.g. no research board exists yet for a future
    // prefetched slate). Never an error; never fabricated.
    return { status: "NO_SNAPSHOT", reason: `No Native projection snapshot exists yet for ${slate.slate_date}.`, playersUpdated: 0 };
  }

  const playerRows = await db.all<CanonicalSlatePlayerRow>("SELECT * FROM slate_players WHERE internal_slate_id = ?", [internalSlateId]);
  const resolvedInternalPlayerIds = playerRows.map((p) => p.internal_player_id).filter((id): id is string => id !== null);
  const mlbIdByInternalPlayerId = await resolveMlbPlayerIds(resolvedInternalPlayerIds);

  const now = new Date().toISOString();
  let playersUpdated = 0;
  await db.transaction(async (tx) => {
    for (const p of playerRows) {
      const mlbPlayerId = p.internal_player_id ? (mlbIdByInternalPlayerId.get(p.internal_player_id) ?? null) : null;
      if (!mlbPlayerId) continue; // unresolved identity -- honestly absent, never guessed.
      const native = nativeByMlbId.get(mlbPlayerId);
      if (!native) continue; // resolved identity, but this real player has no Native projection yet.

      await tx.run(
        `INSERT INTO canonical_slate_player_projections
           (id, internal_slate_id, provider_player_id, source, model_version, projection, ceiling, floor, generated_at, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT (internal_slate_id, provider_player_id, source) DO UPDATE SET
           model_version = excluded.model_version, projection = excluded.projection, ceiling = excluded.ceiling,
           floor = excluded.floor, generated_at = excluded.generated_at, updated_at = excluded.updated_at`,
        [
          crypto.randomUUID(), internalSlateId, p.provider_player_id, NATIVE_SOURCE, native.model_version,
          native.native_projection, native.native_ceiling, native.native_floor, native.generated_at, now, now,
        ],
      );
      playersUpdated += 1;
    }
  });

  return { status: "OK", playersUpdated };
}

export interface CanonicalProjectionRow {
  provider_player_id: string;
  source: string;
  model_version: string | null;
  projection: number | null;
  ceiling: number | null;
  floor: number | null;
  generated_at: string | null;
}

/** Read-only: every persisted projection row for a slate, keyed by
 * provider_player_id (DK id) -- the same key canonicalPostgresBackend.ts
 * already uses for every other per-player join. */
export async function getCanonicalProjectionsForSlate(internalSlateId: string, source: string = NATIVE_SOURCE): Promise<Map<string, CanonicalProjectionRow>> {
  const db = getExecutor();
  const rows = await db.all<CanonicalProjectionRow>(
    "SELECT provider_player_id, source, model_version, projection, ceiling, floor, generated_at FROM canonical_slate_player_projections WHERE internal_slate_id = ? AND source = ?",
    [internalSlateId, source],
  );
  return new Map(rows.map((r) => [r.provider_player_id, r]));
}
