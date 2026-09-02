import crypto from "node:crypto";

import type { CanonicalSlateArtifactDocument, CanonicalSlatePlayerDocument, IdentityMatchDocument } from "./canonicalArtifact";
import { KNOWN_SLATE_SCHEMA_VERSIONS } from "./canonicalArtifact";
import { computeNormalizedHash } from "../canonicalHashing";
import type { SqlExecutor } from "./sqlExecutor";

// M2G / M2J -- the ONE function that writes to the canonical Postgres
// shadow-CURRENT tables (players, player_external_ids, slates,
// slate_players, identity_review_queue -- see
// dashboard/lib/db/migrations-postgres/0010_slate_identity_foundation.sql).
// Used by BOTH:
//   - dashboard/scripts/promote-canonical-slate.ts (live shadow
//     ingestion's promotion step)
//   - dashboard/scripts/rehydrate-canonical-current.ts (M2J: rebuilding
//     CURRENT from a stored NORMALIZED R2 artifact)
// so promotion and rehydration are provably the same operation, never
// two divergent implementations.
//
// This is the Node/TS side of M2 deliberately: this codebase's Postgres
// access has always lived exclusively here (see
// player_identity/persistence.py's own documented reason for never
// adding a Python-to-Postgres dependency) -- canonical_ingestion/ (the
// Python shadow pipeline) only ever writes the immutable NORMALIZED R2
// artifact this function reads.
//
// NEVER wired into poolCache.ts, the optimizer APIs, or any
// customer-facing read path during M2 -- see this milestone's explicit
// customer-protection rules.

export interface PromotionOptions {
  /** Repo-relative NORMALIZED artifact path/key this document was read
   * from -- recorded on the slates row for traceability (M2H). */
  normalizedArtifactPath: string;
  /** RAW manifest path/key, if known -- recorded alongside. */
  rawArtifactPath?: string | null;
  /** M2J: an explicit, operator-only override that skips the
   * older-artifact/no-op guards below. Never set automatically. */
  force?: boolean;
  /** M2J: when given, the artifact's own embedded normalizedHash must
   * match this value exactly or promotion is refused. An INTEGRITY
   * check against a value the operator already trusts (e.g. copied from
   * the ingestion run's own console output) -- independent of
   * `verifyNormalizedHash` below, which re-derives the hash from
   * content instead of comparing against an operator-supplied string. */
  expectedNormalizedHash?: string;
  /** M3H/M3I: when true, independently RECOMPUTES normalizedHash from
   * `artifact.slate`/`artifact.players` (dashboard/lib/canonicalHashing.ts
   * -- verified byte-parity with canonical/hashing.py, see that
   * module's own test suite) and compares it against the artifact's own
   * declared `normalizedHash`. A mismatch means the artifact was
   * tampered with, corrupted in storage, or hand-edited after Python
   * wrote it -- refused unconditionally, `force` does not override this
   * (force only skips the older-artifact/no-op guards, never an
   * integrity check). Not enabled for live automatic promotion (M3B) --
   * the artifact there was written moments ago by the SAME trusted
   * pipeline that computed the hash, so re-verification is redundant
   * work on every single ingestion; scripts/rehydrate-canonical-current.ts
   * (M3I) always sets this true, since rehydration reads an
   * arbitrary-age artifact an operator selected, which is exactly the
   * scenario this guards against. */
  verifyNormalizedHash?: boolean;
}

export interface PromotionResult {
  promoted: boolean;
  reason: string;
  internalSlateId?: string;
  reviewQueueEntriesCreated?: number;
  /** M4E: set when this canonical slate already existed AND the
   * incoming artifact's own computed slateDate differs from the
   * slateDate already stored for it (e.g. a game postponement/
   * reschedule shifted the true first-game-start instant across a
   * calendar boundary). The stored slateDate is NEVER overwritten --
   * see the ON CONFLICT clauses below, which deliberately omit
   * slate_date -- this field exists purely so a caller can observe and
   * report the mismatch (M4G "report what changed if practical")
   * without it ever being treated as a promotion failure. */
  slateDateImmutabilityHeld?: { storedSlateDate: string; incomingSlateDate: string };
}

/** Denormalized, informational index column only -- NOT used for any
 * identity decision (that already happened in Python; see
 * canonical_ingestion/identity_bridge.py). Deliberately NOT claimed to
 * be equivalent to dfs/name_normalization.py::normalize_name -- this is
 * a simpler, display/index-only normalization. */
function normalizeNameForIndex(name: string): string {
  return name.trim().toLowerCase().replace(/\s+/g, " ");
}

async function findCurrentExternalId(tx: SqlExecutor, sport: string, provider: string, externalId: string): Promise<string | null> {
  const row = await tx.get<{ internal_player_id: string }>(
    "SELECT internal_player_id FROM player_external_ids WHERE provider = ? AND external_id = ? AND sport = ? AND is_current = 1",
    [provider, externalId, sport],
  );
  return row?.internal_player_id ?? null;
}

/** M8H -- preserves M1's identity rules: a player may accumulate
 * multiple HISTORICAL provider ids over time (e.g. DraftKings issues a
 * new player_id after a real trade), but the schema's own Invariant 2
 * (idx_player_external_ids_current_per_player, migrations/0009) allows
 * only ONE row per (internal_player_id, provider, sport) to be
 * is_current=1 at once. If this player already has a DIFFERENT current
 * external id for this exact provider, that old row is superseded
 * (is_current=0, valid_to=now) -- never deleted, never left dangling --
 * before the new one is inserted as current. This is the SAME player
 * (mlbam id decided that already, upstream in resolveInternalPlayerId);
 * a team change is metadata, never grounds for a second canonical
 * identity (M8E). No `UNIQUE(internal_player_id, provider)` constraint
 * is restored here -- multiple non-current rows for the same provider
 * remain fully legal, exactly as M1 specified. */
async function attachExternalIdIfMissing(
  tx: SqlExecutor, internalPlayerId: string, sport: string, provider: string, externalId: string, externalIdType: string,
  matchMethod: string, matchConfidence: number, now: string,
): Promise<void> {
  const existing = await tx.get<{ id: string }>(
    "SELECT id FROM player_external_ids WHERE provider = ? AND external_id = ? AND sport = ? AND is_current = 1",
    [provider, externalId, sport],
  );
  if (existing) return;

  const priorCurrent = await tx.get<{ id: string; external_id: string }>(
    "SELECT id, external_id FROM player_external_ids WHERE internal_player_id = ? AND provider = ? AND sport = ? AND is_current = 1",
    [internalPlayerId, provider, sport],
  );
  if (priorCurrent && priorCurrent.external_id !== externalId) {
    await tx.run(
      "UPDATE player_external_ids SET is_current = 0, valid_to = ?, updated_at = ? WHERE id = ?",
      [now, now, priorCurrent.id],
    );
  }

  await tx.run(
    `INSERT INTO player_external_ids
      (id, internal_player_id, sport, provider, external_id, external_id_type, match_method, match_confidence, review_status, is_current, valid_from, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'AUTO_APPROVED', 1, ?, ?, ?)`,
    [crypto.randomUUID(), internalPlayerId, sport, provider, externalId, externalIdType, matchMethod, matchConfidence, now, now, now],
  );
}

/** Resolves the internal_player_id for one slate player using ONLY the
 * deterministic decision canonical_ingestion/identity_bridge.py already
 * computed (`match`) -- this function NEVER re-decides or fuzzy-matches
 * on its own. It DOES check for a pre-existing crosswalk row first
 * (stability across repeated ingestions -- once a DK id is resolved, it
 * stays resolved to the same internal player forever, even if a later
 * fetch's own match attempt came back UNRESOLVED for some reason). */
async function resolveInternalPlayerId(
  tx: SqlExecutor, sport: string, player: CanonicalSlatePlayerDocument, match: IdentityMatchDocument | undefined, now: string,
): Promise<string | null> {
  const dkHint = match?.externalIdHints.find((h) => h.provider === "draftkings");
  const dkExternalId = dkHint?.externalId ?? player.providerPlayerId;

  const existingByDk = await findCurrentExternalId(tx, sport, "draftkings", dkExternalId);
  if (existingByDk) return existingByDk;

  if (!match || match.identityStatus !== "RESOLVED") {
    return null; // UNRESOLVED or REVIEW_REQUIRED, and no prior crosswalk row exists -- servable, unresolved.
  }

  const mlbamHint = match.externalIdHints.find((h) => h.provider === "mlbam");
  if (mlbamHint) {
    const existingByMlbam = await findCurrentExternalId(tx, sport, "mlbam", mlbamHint.externalId);
    if (existingByMlbam) {
      await attachExternalIdIfMissing(tx, existingByMlbam, sport, "draftkings", dkExternalId, "player_id", match.matchMethod ?? "exact_deterministic_source_mapping", match.matchConfidence ?? 1.0, now);
      return existingByMlbam;
    }
  }

  // Brand new player -- mint.
  const internalPlayerId = crypto.randomUUID();
  await tx.run(
    "INSERT INTO players (internal_player_id, sport, canonical_name, normalized_name, current_team, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
    [internalPlayerId, sport, player.name, normalizeNameForIndex(player.name), player.team, now, now],
  );
  await attachExternalIdIfMissing(tx, internalPlayerId, sport, "draftkings", dkExternalId, "player_id", match.matchMethod ?? "exact_deterministic_source_mapping", match.matchConfidence ?? 1.0, now);
  if (mlbamHint) {
    await attachExternalIdIfMissing(tx, internalPlayerId, sport, "mlbam", mlbamHint.externalId, "mlbam_id", match.matchMethod ?? "exact_deterministic_source_mapping", match.matchConfidence ?? 1.0, now);
  }
  return internalPlayerId;
}

/** Creates a PENDING identity_review_queue row for `player`, UNLESS one
 * already exists for the same (sport, provider, externalId) -- avoids
 * duplicate review-queue spam across repeated ingestions of the same
 * ambiguous player (M2K's explicit requirement). Returns whether a new
 * row was actually created. */
async function createReviewQueueEntryIfNeeded(
  tx: SqlExecutor, sport: string, player: CanonicalSlatePlayerDocument, match: IdentityMatchDocument, now: string,
): Promise<boolean> {
  const dkHint = match.externalIdHints.find((h) => h.provider === "draftkings");
  const externalId = dkHint?.externalId ?? player.providerPlayerId;

  const existing = await tx.get<{ id: string }>(
    "SELECT id FROM identity_review_queue WHERE sport = ? AND provider = 'draftkings' AND external_id = ? AND status = 'PENDING'",
    [sport, externalId],
  );
  if (existing) return false;

  await tx.run(
    `INSERT INTO identity_review_queue
      (id, sport, provider, external_id, provider_player_name, provider_team, provider_position, candidate_internal_player_id, reason, status, created_at, updated_at)
     VALUES (?, ?, 'draftkings', ?, ?, ?, NULL, NULL, ?, 'PENDING', ?, ?)`,
    [crypto.randomUUID(), sport, externalId, player.name, player.team, match.reason ?? "Ambiguous identity match -- needs human review.", now, now],
  );
  return true;
}

/** M3E: records a REJECTED-validation attempt (a routine automatic-path
 * outcome, e.g. DK returning a Snake/Showdown-format DraftGroup that
 * fails structural validation) as a full slates row -- `slate.*`'s
 * shape is trustworthy here (schemaVersion is known-good; only content
 * validation failed), so a real row can be written for diagnosability,
 * with consecutive_failures incremented and no player/identity sync
 * attempted. Deliberately NOT done for an unknown schemaVersion (the
 * artifact's shape itself isn't trustworthy) or a hash-mismatch
 * rehydration refusal (an operator-facing integrity guard, not a
 * routine automatic outcome) -- those stay pure no-DB-write refusals. */
async function recordRejectedAttempt(db: SqlExecutor, artifact: CanonicalSlateArtifactDocument, errorType: string, errorSummary: string): Promise<void> {
  const slate = artifact.slate;
  const now = new Date().toISOString();
  const proposedInternalSlateId = slate.internalSlateId || crypto.randomUUID();
  // raw_hash/normalized_hash are DELIBERATELY never set from a rejected
  // attempt (NULL on first insert, left untouched by the ON CONFLICT
  // branch below) -- their meaning everywhere else in this schema is
  // "the hash of the CURRENTLY PROMOTED content." A rejected artifact
  // was never promoted; letting its hash leak into these columns could
  // cause a LATER genuinely-valid artifact that happens to normalize to
  // the same hash to be incorrectly treated as an identical-hash no-op.
  await db.run(
    `INSERT INTO slates (
       internal_slate_id, sport, site, provider, provider_slate_id, slate_name, slate_date, first_game_start_utc,
       game_count, game_ids_json, salary_cap, roster_template_json, source_provenance, validation_state,
       validation_findings_json, schema_version, raw_hash, normalized_hash, fetched_at,
       last_attempt_at, last_failure_at, consecutive_failures, last_error_type, last_error_summary,
       created_at, updated_at
     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, 1, ?, ?, ?, ?)
     ON CONFLICT (sport, site, provider, provider_slate_id) DO UPDATE SET
       slate_name = excluded.slate_name, first_game_start_utc = excluded.first_game_start_utc,
       game_count = excluded.game_count, game_ids_json = excluded.game_ids_json, salary_cap = excluded.salary_cap,
       roster_template_json = excluded.roster_template_json, source_provenance = excluded.source_provenance,
       validation_state = excluded.validation_state, validation_findings_json = excluded.validation_findings_json,
       schema_version = excluded.schema_version,
       last_attempt_at = excluded.last_attempt_at, last_failure_at = excluded.last_failure_at,
       consecutive_failures = slates.consecutive_failures + 1,
       last_error_type = excluded.last_error_type, last_error_summary = excluded.last_error_summary,
       updated_at = excluded.updated_at`,
    [
      proposedInternalSlateId, slate.sport, slate.site, slate.provider, slate.providerSlateId, slate.slateName, slate.slateDate,
      slate.firstGameStartUtc, slate.gameCount, JSON.stringify(slate.gameIds), slate.salaryCap, slate.rosterTemplate ? JSON.stringify(slate.rosterTemplate) : null,
      slate.sourceProvenance, slate.validationState, JSON.stringify(slate.validationFindings), artifact.schemaVersion,
      slate.fetchedAt, now, now, errorType, errorSummary, now, now,
    ],
  );
}

/** M3E: a no-op outcome (identical hash, or an older artifact refused)
 * is NOT a failure -- but is still a real attempt worth recording for
 * liveness/staleness monitoring, without touching consecutive_failures
 * or any player/identity data.
 *
 * T3 Step 7: ALSO advances last_validated_at. A semantic no-op means the
 * external worker successfully re-checked the real DraftKings source
 * (or, for --force rehydration, re-confirmed a stored artifact) and
 * found the content genuinely unchanged -- a real, honest revalidation
 * event, distinct from fetched_at/promoted_at (the immutable "when was
 * this content acquired" facts, which correctly never move for
 * identical content). canonicalPostgresBackend.ts's freshness policy
 * reads last_validated_at so a slate that is actively, successfully
 * being re-checked never ages toward "stale_expired" merely because its
 * own content happens to be stable. */
async function recordNoOpAttempt(db: SqlExecutor, internalSlateId: string): Promise<void> {
  const now = new Date().toISOString();
  await db.run("UPDATE slates SET last_attempt_at = ?, last_validated_at = ? WHERE internal_slate_id = ?", [now, now, internalSlateId]);
}

export async function promoteCanonicalArtifact(
  db: SqlExecutor, artifact: CanonicalSlateArtifactDocument, options: PromotionOptions,
): Promise<PromotionResult> {
  if (!KNOWN_SLATE_SCHEMA_VERSIONS.has(artifact.schemaVersion)) {
    return { promoted: false, reason: `Unknown schemaVersion '${artifact.schemaVersion}' -- refusing to promote an artifact this code doesn't know how to read.` };
  }
  if (options.expectedNormalizedHash && options.expectedNormalizedHash !== artifact.normalizedHash) {
    return { promoted: false, reason: "normalizedHash does not match the operator-supplied expected value -- refusing to promote." };
  }
  if (options.verifyNormalizedHash) {
    const recomputed = computeNormalizedHash(artifact.slate as unknown as Record<string, unknown>, artifact.players as unknown as Array<Record<string, unknown>>);
    if (recomputed !== artifact.normalizedHash) {
      return {
        promoted: false,
        reason: `Independently recomputed normalizedHash ('${recomputed}') does not match the artifact's own declared normalizedHash ('${artifact.normalizedHash}') -- the artifact appears tampered or corrupted. Refusing to promote/rehydrate.`,
      };
    }
  }
  if (artifact.slate.validationState !== "VALID") {
    await recordRejectedAttempt(db, artifact, "VALIDATION_REJECTED", `slate.validationState was '${artifact.slate.validationState}': ${artifact.slate.validationFindings.join("; ") || "no findings given"}`);
    return { promoted: false, reason: `slate.validationState is '${artifact.slate.validationState}', not VALID -- refusing to promote.` };
  }

  return db.transaction(async (tx) => {
    const slate = artifact.slate;
    const existing = await tx.get<{ internal_slate_id: string; fetched_at: string | null; normalized_hash: string | null; slate_date: string }>(
      "SELECT internal_slate_id, fetched_at, normalized_hash, slate_date FROM slates WHERE sport = ? AND site = ? AND provider = ? AND provider_slate_id = ?",
      [slate.sport, slate.site, slate.provider, slate.providerSlateId],
    );
    // M4E: providerSlateId identity is looked up (immediately above)
    // BEFORE any slateDate decision is made, and the stored slate_date
    // is never included in the ON CONFLICT DO UPDATE SET clause below --
    // a game reschedule/postponement that shifts the newly computed
    // slateDate is recorded here for observability only, never applied.
    const slateDateImmutabilityHeld =
      existing && existing.slate_date !== slate.slateDate
        ? { storedSlateDate: existing.slate_date, incomingSlateDate: slate.slateDate }
        : undefined;

    if (existing && !options.force) {
      if (existing.normalized_hash != null && existing.normalized_hash === artifact.normalizedHash) {
        await recordNoOpAttempt(tx, existing.internal_slate_id);
        return { promoted: false, reason: "identical normalizedHash to the currently-promoted version -- semantic no-op.", internalSlateId: existing.internal_slate_id, slateDateImmutabilityHeld };
      }
      if (existing.fetched_at && slate.fetchedAt && existing.fetched_at > slate.fetchedAt) {
        await recordNoOpAttempt(tx, existing.internal_slate_id);
        return { promoted: false, reason: "incoming artifact is older than the currently-promoted version -- CURRENT not moved backward.", internalSlateId: existing.internal_slate_id, slateDateImmutabilityHeld };
      }
    }

    const now = new Date().toISOString();
    const proposedInternalSlateId = slate.internalSlateId || crypto.randomUUID();

    // M3E: resolve identity for every player FIRST (independent of the
    // slates/slate_players rows -- only touches players/
    // player_external_ids/identity_review_queue), so the counts
    // recorded on `slates` below reflect the REAL final identityStatus
    // each player gets (which can differ from artifact.identityMatches'
    // own status -- resolveInternalPlayerId can upgrade an UNRESOLVED
    // match to RESOLVED via a pre-existing crosswalk row), never a
    // possibly-stale pre-resolution estimate.
    let reviewQueueEntriesCreated = 0;
    const resolvedPlayers: Array<{ player: CanonicalSlatePlayerDocument; internalPlayerId: string | null; identityStatus: CanonicalSlatePlayerDocument["identityStatus"] }> = [];
    for (const player of artifact.players) {
      const match = artifact.identityMatches[player.providerPlayerId];
      const internalPlayerId = await resolveInternalPlayerId(tx, slate.sport, player, match, now);

      let identityStatus: CanonicalSlatePlayerDocument["identityStatus"];
      if (internalPlayerId) {
        identityStatus = "RESOLVED";
      } else if (match?.identityStatus === "REVIEW_REQUIRED") {
        identityStatus = "REVIEW_REQUIRED";
        if (await createReviewQueueEntryIfNeeded(tx, slate.sport, player, match, now)) reviewQueueEntriesCreated += 1;
      } else {
        identityStatus = "UNRESOLVED";
      }
      resolvedPlayers.push({ player, internalPlayerId, identityStatus });
    }

    const playerCount = resolvedPlayers.length;
    const resolvedCount = resolvedPlayers.filter((p) => p.identityStatus === "RESOLVED").length;
    const reviewRequiredCount = resolvedPlayers.filter((p) => p.identityStatus === "REVIEW_REQUIRED").length;
    const unresolvedCount = playerCount - resolvedCount - reviewRequiredCount;
    const isSemanticDuplicate = artifact.isSemanticDuplicate ? 1 : 0;

    const upserted = await tx.get<{ internal_slate_id: string }>(
      `INSERT INTO slates (
         internal_slate_id, sport, site, provider, provider_slate_id, slate_name, slate_date, first_game_start_utc,
         game_count, game_ids_json, salary_cap, roster_template_json, source_provenance, validation_state,
         validation_findings_json, schema_version, raw_hash, normalized_hash, fetched_at,
         current_normalized_artifact_path, current_raw_artifact_path, promoted_at, last_validated_at,
         last_attempt_at, last_success_at, consecutive_failures, last_error_type, last_error_summary,
         player_count, resolved_identity_count, unresolved_identity_count, review_required_count, is_semantic_duplicate,
         created_at, updated_at
       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT (sport, site, provider, provider_slate_id) DO UPDATE SET
         slate_name = excluded.slate_name, first_game_start_utc = excluded.first_game_start_utc,
         game_count = excluded.game_count, game_ids_json = excluded.game_ids_json, salary_cap = excluded.salary_cap,
         roster_template_json = excluded.roster_template_json, source_provenance = excluded.source_provenance,
         validation_state = excluded.validation_state, validation_findings_json = excluded.validation_findings_json,
         schema_version = excluded.schema_version, raw_hash = excluded.raw_hash, normalized_hash = excluded.normalized_hash,
         fetched_at = excluded.fetched_at, current_normalized_artifact_path = excluded.current_normalized_artifact_path,
         current_raw_artifact_path = excluded.current_raw_artifact_path, promoted_at = excluded.promoted_at,
         last_validated_at = excluded.last_validated_at,
         last_attempt_at = excluded.last_attempt_at, last_success_at = excluded.last_success_at,
         consecutive_failures = 0, last_error_type = NULL, last_error_summary = NULL,
         player_count = excluded.player_count, resolved_identity_count = excluded.resolved_identity_count,
         unresolved_identity_count = excluded.unresolved_identity_count, review_required_count = excluded.review_required_count,
         is_semantic_duplicate = excluded.is_semantic_duplicate, updated_at = excluded.updated_at
       RETURNING internal_slate_id`,
      [
        proposedInternalSlateId, slate.sport, slate.site, slate.provider, slate.providerSlateId, slate.slateName, slate.slateDate,
        slate.firstGameStartUtc, slate.gameCount, JSON.stringify(slate.gameIds), slate.salaryCap, slate.rosterTemplate ? JSON.stringify(slate.rosterTemplate) : null,
        slate.sourceProvenance, slate.validationState, JSON.stringify(slate.validationFindings), artifact.schemaVersion, artifact.rawHash, artifact.normalizedHash,
        slate.fetchedAt, options.normalizedArtifactPath, options.rawArtifactPath ?? null, now, now,
        now, now,
        playerCount, resolvedCount, unresolvedCount, reviewRequiredCount, isSemanticDuplicate, now, now,
      ],
    );
    // internal_slate_id is NEVER included in the DO UPDATE SET clause
    // above -- an existing row's canonical id is never overwritten by a
    // later ingestion's own (necessarily different) proposed uuid. This
    // is M2D's actual stability mechanism -- see canonical_ingestion/
    // normalize.py's docstring for why Python doesn't need to query
    // Postgres to achieve the same guarantee.
    const internalSlateId = upserted!.internal_slate_id;

    // M7C: UPSERT per player (never a blanket DELETE-then-reinsert-all)
    // so a re-promotion driven by a genuine ACQUISITION change (salary/
    // roster/identity) does NOT wipe out RESEARCH-derived state
    // (eligibility_status/optimizer_eligible/batting_order/
    // eligibility_computed_at, and any game_id already resolved by
    // scripts/compute_canonical_eligibility.py) that a separate,
    // independent process already persisted on this exact row -- see
    // canonicalEligibility.ts's own docstring. Confirmed live in
    // production during M6: a natural re-promotion of a still-being-
    // refreshed tomorrow slate silently reset a real, just-computed
    // eligibility_computed_at back to null, exactly because the OLD
    // DELETE+reinsert-all pattern below discarded it. `game_id` is only
    // overwritten when the incoming artifact actually supplies one
    // (COALESCE onto the existing value) -- acquisition does not
    // resolve game_id today (M6B did that ONLY inside the eligibility
    // bridge), so this keeps a real, already-resolved game_id from
    // being reset to null by an unrelated salary refresh, while still
    // allowing a FUTURE acquisition-time game_id resolution to take
    // effect once/if it exists. Eligibility/batting_order columns are
    // NEVER included in this SET clause at all -- only
    // canonicalEligibility.ts ever writes them.
    const incomingProviderPlayerIds = resolvedPlayers.map(({ player }) => player.providerPlayerId);
    if (incomingProviderPlayerIds.length > 0) {
      const placeholders = incomingProviderPlayerIds.map(() => "?").join(", ");
      await tx.run(
        `DELETE FROM slate_players WHERE internal_slate_id = ? AND provider_player_id NOT IN (${placeholders})`,
        [internalSlateId, ...incomingProviderPlayerIds],
      );
    } else {
      await tx.run("DELETE FROM slate_players WHERE internal_slate_id = ?", [internalSlateId]);
    }

    for (const { player, internalPlayerId, identityStatus } of resolvedPlayers) {
      await tx.run(
        `INSERT INTO slate_players
          (internal_slate_id, provider_player_id, internal_player_id, provider_draftable_ids_json, name, team, opponent, game_id, salary,
           position_eligibility_json, roster_slot_eligibility_json, identity_status, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT (internal_slate_id, provider_player_id) DO UPDATE SET
           internal_player_id = excluded.internal_player_id, provider_draftable_ids_json = excluded.provider_draftable_ids_json,
           name = excluded.name, team = excluded.team, opponent = excluded.opponent,
           game_id = COALESCE(excluded.game_id, slate_players.game_id),
           salary = excluded.salary, position_eligibility_json = excluded.position_eligibility_json,
           roster_slot_eligibility_json = excluded.roster_slot_eligibility_json, identity_status = excluded.identity_status,
           updated_at = excluded.updated_at`,
        [
          internalSlateId, player.providerPlayerId, internalPlayerId, JSON.stringify(player.providerDraftableIds), player.name, player.team,
          player.opponent, player.gameId, player.salary, JSON.stringify(player.positionEligibility), JSON.stringify(player.rosterSlotEligibility),
          identityStatus, now, now,
        ],
      );
    }

    return {
      promoted: true,
      reason: existing ? "Updated existing canonical slate." : "Created new canonical slate.",
      internalSlateId,
      reviewQueueEntriesCreated,
      slateDateImmutabilityHeld,
    };
  });
}
