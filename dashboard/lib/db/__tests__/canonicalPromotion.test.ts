import { beforeEach, describe, expect, it } from "vitest";

import type { CanonicalSlateArtifactDocument } from "../canonicalArtifact";
import { promoteCanonicalArtifact } from "../canonicalPromotion";
import { __resetDbForTests, getDb } from "../client";
import { __resetExecutorForTests, getExecutor } from "../executor";
import { computeNormalizedHash } from "../../canonicalHashing";

/** Real, content-derived normalizedHash for `artifact` -- baseArtifact()'s
 * default "norm-hash-1" is a plain placeholder string, not actually
 * derived from its own content, so any verifyNormalizedHash:true test
 * must overwrite it with the real value first or it will always look
 * "tampered." */
function withRealHash(artifact: CanonicalSlateArtifactDocument): CanonicalSlateArtifactDocument {
  artifact.normalizedHash = computeNormalizedHash(artifact.slate as unknown as Record<string, unknown>, artifact.players as unknown as Array<Record<string, unknown>>);
  return artifact;
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

function baseArtifact(overrides: Partial<CanonicalSlateArtifactDocument> = {}): CanonicalSlateArtifactDocument {
  return {
    schemaVersion: "slate_normalized_v1",
    rawHash: "raw-hash-1",
    normalizedHash: "norm-hash-1",
    slate: {
      internalSlateId: "proposed-uuid-1",
      sport: "MLB",
      site: "draftkings",
      provider: "draftkings_unofficial",
      providerSlateId: "152904",
      slateName: "Main",
      slateDate: "2026-08-31",
      firstGameStartUtc: "2026-08-31T23:05:00Z",
      gameCount: 1,
      gameIds: ["g1"],
      salaryCap: 50000,
      rosterTemplate: { P: 2, OF: 3 },
      sourceProvenance: "DRAFTKINGS_UNOFFICIAL_LIVE",
      validationState: "VALID",
      validationFindings: [],
      fetchedAt: "2026-08-31T20:00:00.000Z",
    },
    players: [
      {
        internalSlateId: "proposed-uuid-1", internalPlayerId: null, providerPlayerId: "999",
        providerDraftableIds: ["101", "102"], name: "Flex Player", team: "BOS", opponent: "TOR",
        gameId: null, salary: 4500, positionEligibility: ["1B", "OF"], rosterSlotEligibility: [],
        identityStatus: "UNRESOLVED",
      },
    ],
    identityMatches: {
      "999": { identityStatus: "UNRESOLVED", matchMethod: null, matchConfidence: null, externalIdHints: [{ provider: "draftkings", externalId: "999", externalIdType: "player_id" }], candidateMlbPlayerIds: [], reason: "no match" },
    },
    ...overrides,
  };
}

function opts(overrides: Partial<Parameters<typeof promoteCanonicalArtifact>[2]> = {}) {
  return { normalizedArtifactPath: "normalized/MLB/2026-08-31/draftkings_unofficial/152904/x.json", rawArtifactPath: "raw/x", ...overrides };
}

describe("promoteCanonicalArtifact", () => {
  it("creates a new canonical slate + player rows, nullable internalPlayerId accepted", async () => {
    const db = getExecutor();
    const result = await promoteCanonicalArtifact(db, baseArtifact(), opts());
    expect(result.promoted).toBe(true);
    expect(result.internalSlateId).toBeTruthy();

    const slateRow = getDb().prepare("SELECT * FROM slates WHERE internal_slate_id = ?").get(result.internalSlateId!) as Record<string, unknown>;
    expect(slateRow.provider_slate_id).toBe("152904");
    expect(slateRow.current_normalized_artifact_path).toBe(opts().normalizedArtifactPath);

    const playerRow = getDb().prepare("SELECT * FROM slate_players WHERE internal_slate_id = ?").get(result.internalSlateId!) as Record<string, unknown>;
    expect(playerRow.internal_player_id).toBeNull();
    expect(playerRow.identity_status).toBe("UNRESOLVED");
  });

  it("rejects an unknown schemaVersion without writing anything", async () => {
    const db = getExecutor();
    const result = await promoteCanonicalArtifact(db, baseArtifact({ schemaVersion: "slate_normalized_v99" }), opts());
    expect(result.promoted).toBe(false);
    const count = (getDb().prepare("SELECT COUNT(*) as c FROM slates").get() as { c: number }).c;
    expect(count).toBe(0);
  });

  it("rejects a REJECTED validationState -- never promoted, never syncs slate_players", async () => {
    const db = getExecutor();
    const artifact = baseArtifact();
    artifact.slate.validationState = "REJECTED";
    artifact.slate.validationFindings = ["structural validation failed: bad roster template"];
    const result = await promoteCanonicalArtifact(db, artifact, opts());
    expect(result.promoted).toBe(false);
    expect(result.internalSlateId).toBeUndefined();

    const players = (getDb().prepare("SELECT COUNT(*) as c FROM slate_players").get() as { c: number }).c;
    expect(players).toBe(0); // never synced -- a rejected slate has no promoted player set
  });

  it("M3E: a REJECTED validationState IS recorded as a failed attempt for observability", async () => {
    const db = getExecutor();
    const artifact = baseArtifact();
    artifact.slate.validationState = "REJECTED";
    artifact.slate.validationFindings = ["structural validation failed: bad roster template"];
    await promoteCanonicalArtifact(db, artifact, opts());

    const row = getDb().prepare("SELECT validation_state, consecutive_failures, last_error_type, last_error_summary, last_attempt_at, last_failure_at FROM slates WHERE provider_slate_id = '152904'").get() as Record<string, unknown>;
    expect(row.validation_state).toBe("REJECTED");
    expect(row.consecutive_failures).toBe(1);
    expect(row.last_error_type).toBe("VALIDATION_REJECTED");
    expect(String(row.last_error_summary)).toMatch(/bad roster template/);
    expect(row.last_attempt_at).toBeTruthy();
    expect(row.last_failure_at).toBeTruthy();
  });

  it("M3E: consecutive_failures increments across repeated REJECTED attempts and resets on a later success", async () => {
    const db = getExecutor();
    const rejected = baseArtifact();
    rejected.slate.validationState = "REJECTED";
    await promoteCanonicalArtifact(db, rejected, opts());
    await promoteCanonicalArtifact(db, rejected, opts());

    const afterRejections = getDb().prepare("SELECT consecutive_failures FROM slates WHERE provider_slate_id = '152904'").get() as { consecutive_failures: number };
    expect(afterRejections.consecutive_failures).toBe(2);

    const success = baseArtifact();
    success.slate.fetchedAt = "2026-08-31T22:00:00.000Z";
    const result = await promoteCanonicalArtifact(db, success, opts());
    expect(result.promoted).toBe(true);

    const afterSuccess = getDb().prepare("SELECT consecutive_failures, last_error_type FROM slates WHERE provider_slate_id = '152904'").get() as { consecutive_failures: number; last_error_type: string | null };
    expect(afterSuccess.consecutive_failures).toBe(0);
    expect(afterSuccess.last_error_type).toBeNull();
  });

  it("M3E: successful promotion records player/identity counts and last_success_at", async () => {
    const db = getExecutor();
    const result = await promoteCanonicalArtifact(db, baseArtifact(), opts());
    const row = getDb().prepare("SELECT player_count, resolved_identity_count, unresolved_identity_count, review_required_count, is_semantic_duplicate, last_success_at, last_attempt_at FROM slates WHERE internal_slate_id = ?").get(result.internalSlateId!) as Record<string, unknown>;
    expect(row.player_count).toBe(1);
    expect(row.unresolved_identity_count).toBe(1);
    expect(row.resolved_identity_count).toBe(0);
    expect(row.review_required_count).toBe(0);
    expect(row.is_semantic_duplicate).toBe(0);
    expect(row.last_success_at).toBeTruthy();
    expect(row.last_attempt_at).toBeTruthy();
  });

  it("M3E: a semantic no-op still updates last_attempt_at without touching consecutive_failures", async () => {
    const db = getExecutor();
    const first = await promoteCanonicalArtifact(db, baseArtifact(), opts());
    const before = getDb().prepare("SELECT last_attempt_at FROM slates WHERE internal_slate_id = ?").get(first.internalSlateId!) as { last_attempt_at: string };

    await new Promise((resolve) => setTimeout(resolve, 5));
    const second = await promoteCanonicalArtifact(db, baseArtifact(), opts());
    expect(second.promoted).toBe(false);

    const after = getDb().prepare("SELECT last_attempt_at, consecutive_failures FROM slates WHERE internal_slate_id = ?").get(first.internalSlateId!) as { last_attempt_at: string; consecutive_failures: number };
    expect(after.last_attempt_at).not.toBe(before.last_attempt_at);
    expect(after.consecutive_failures).toBe(0);
  });

  it("M2D: repeated ingestion of the same provider slate reuses internalSlateId, never mints a new one", async () => {
    const db = getExecutor();
    const firstArtifact = baseArtifact();
    firstArtifact.slate.internalSlateId = "proposal-a";
    const first = await promoteCanonicalArtifact(db, firstArtifact, opts());

    const secondArtifact = baseArtifact();
    secondArtifact.slate.internalSlateId = "proposal-b"; // a DIFFERENT proposed uuid
    secondArtifact.normalizedHash = "norm-hash-2"; // genuinely different content, so this isn't a no-op
    secondArtifact.slate.fetchedAt = "2026-08-31T22:00:00.000Z";
    const second = await promoteCanonicalArtifact(db, secondArtifact, opts());

    expect(second.promoted).toBe(true);
    expect(first.internalSlateId).toBe(second.internalSlateId); // the pre-existing row's id wins, never proposal-b

    const rows = getDb().prepare("SELECT COUNT(*) as c FROM slates WHERE provider_slate_id = '152904'").get() as { c: number };
    expect(rows.c).toBe(1); // never duplicated
  });

  it("a genuinely DIFFERENT DraftGroup gets a different internalSlateId", async () => {
    const db = getExecutor();
    const first = await promoteCanonicalArtifact(db, baseArtifact(), opts());
    const otherSlate = baseArtifact();
    otherSlate.slate.internalSlateId = "proposed-uuid-2"; // a distinct proposal, as a real fresh crypto.randomUUID() would be
    otherSlate.slate.providerSlateId = "152905";
    otherSlate.normalizedHash = "different-hash";
    const second = await promoteCanonicalArtifact(db, otherSlate, opts());
    expect(first.internalSlateId).not.toBe(second.internalSlateId);
  });

  it("identical normalizedHash is treated as a semantic no-op (no duplicate rows)", async () => {
    const db = getExecutor();
    await promoteCanonicalArtifact(db, baseArtifact(), opts());
    const second = await promoteCanonicalArtifact(db, baseArtifact(), opts());
    expect(second.promoted).toBe(false);
    expect(second.reason).toMatch(/no-op/);
    const count = (getDb().prepare("SELECT COUNT(*) as c FROM slates").get() as { c: number }).c;
    expect(count).toBe(1);
  });

  it("an older fetchedAt is rejected and does not move CURRENT backward", async () => {
    const db = getExecutor();
    const newer = baseArtifact();
    newer.slate.fetchedAt = "2026-08-31T21:00:00.000Z";
    await promoteCanonicalArtifact(db, newer, opts());

    const older = baseArtifact();
    older.slate.fetchedAt = "2026-08-31T18:00:00.000Z"; // earlier than what's already promoted
    older.normalizedHash = "some-other-hash"; // genuinely different content, but OLDER
    const result = await promoteCanonicalArtifact(db, older, opts());

    expect(result.promoted).toBe(false);
    expect(result.reason).toMatch(/older/);
    const slateRow = getDb().prepare("SELECT fetched_at FROM slates WHERE provider_slate_id = '152904'").get() as { fetched_at: string };
    expect(slateRow.fetched_at).toBe("2026-08-31T21:00:00.000Z"); // unchanged
  });

  it("a newer fetchedAt with different content succeeds and fully synchronizes slate_players", async () => {
    const db = getExecutor();
    await promoteCanonicalArtifact(db, baseArtifact(), opts());

    const updated = baseArtifact();
    updated.slate.fetchedAt = "2026-08-31T22:00:00.000Z";
    updated.normalizedHash = "norm-hash-2";
    updated.players = [
      { internalSlateId: "x", internalPlayerId: null, providerPlayerId: "888", providerDraftableIds: ["201"], name: "New Player", team: "TOR", opponent: "BOS", gameId: null, salary: 5000, positionEligibility: ["SS"], rosterSlotEligibility: [], identityStatus: "UNRESOLVED" },
    ];
    updated.identityMatches = { "888": { identityStatus: "UNRESOLVED", matchMethod: null, matchConfidence: null, externalIdHints: [{ provider: "draftkings", externalId: "888", externalIdType: "player_id" }], candidateMlbPlayerIds: [], reason: null } };

    const result = await promoteCanonicalArtifact(db, updated, opts());
    expect(result.promoted).toBe(true);

    const players = getDb().prepare("SELECT provider_player_id FROM slate_players WHERE internal_slate_id = ?").all(result.internalSlateId!) as Array<{ provider_player_id: string }>;
    expect(players.map((p) => p.provider_player_id)).toEqual(["888"]); // old player (999) fully removed, never left stale
  });

  it("resolved identity mints a Player row and attaches both external ids", async () => {
    const db = getExecutor();
    const artifact = baseArtifact();
    artifact.players[0].identityStatus = "RESOLVED";
    artifact.identityMatches["999"] = {
      identityStatus: "RESOLVED", matchMethod: "exact_deterministic_source_mapping", matchConfidence: 1.0,
      externalIdHints: [{ provider: "draftkings", externalId: "999", externalIdType: "player_id" }, { provider: "mlbam", externalId: "660271", externalIdType: "mlbam_id" }],
      candidateMlbPlayerIds: ["660271"], reason: null,
    };
    const result = await promoteCanonicalArtifact(db, artifact, opts());
    const playerRow = getDb().prepare("SELECT internal_player_id, identity_status FROM slate_players WHERE internal_slate_id = ?").get(result.internalSlateId!) as Record<string, unknown>;
    expect(playerRow.internal_player_id).toBeTruthy();
    expect(playerRow.identity_status).toBe("RESOLVED");

    const externalIds = getDb().prepare("SELECT provider, external_id FROM player_external_ids WHERE internal_player_id = ? ORDER BY provider").all(playerRow.internal_player_id as string) as Array<{ provider: string; external_id: string }>;
    expect(externalIds).toEqual([
      { provider: "draftkings", external_id: "999" },
      { provider: "mlbam", external_id: "660271" },
    ]);
  });

  it("review-required creates exactly one identity_review_queue entry, never duplicated on re-ingestion", async () => {
    const db = getExecutor();
    const artifact = baseArtifact();
    artifact.players[0].identityStatus = "REVIEW_REQUIRED";
    artifact.identityMatches["999"] = {
      identityStatus: "REVIEW_REQUIRED", matchMethod: null, matchConfidence: null,
      externalIdHints: [{ provider: "draftkings", externalId: "999", externalIdType: "player_id" }],
      candidateMlbPlayerIds: ["1", "2"], reason: "2 candidates share this exact name/team.",
    };
    const first = await promoteCanonicalArtifact(db, artifact, opts());
    expect(first.reviewQueueEntriesCreated).toBe(1);

    const artifact2 = baseArtifact();
    artifact2.normalizedHash = "norm-hash-2";
    artifact2.slate.fetchedAt = "2026-08-31T22:00:00.000Z";
    artifact2.players[0].identityStatus = "REVIEW_REQUIRED";
    artifact2.identityMatches["999"] = artifact.identityMatches["999"];
    const second = await promoteCanonicalArtifact(db, artifact2, opts());
    expect(second.reviewQueueEntriesCreated).toBe(0); // already PENDING -- never spammed

    const queueCount = (getDb().prepare("SELECT COUNT(*) as c FROM identity_review_queue WHERE status = 'PENDING'").get() as { c: number }).c;
    expect(queueCount).toBe(1);
  });

  it("M2J: expectedNormalizedHash mismatch is rejected without writing anything", async () => {
    const db = getExecutor();
    const result = await promoteCanonicalArtifact(db, baseArtifact(), opts({ expectedNormalizedHash: "not-the-real-hash" }));
    expect(result.promoted).toBe(false);
    const count = (getDb().prepare("SELECT COUNT(*) as c FROM slates").get() as { c: number }).c;
    expect(count).toBe(0);
  });

  it("M2J: --force overrides the older-artifact guard for an explicit operator rehydration", async () => {
    const db = getExecutor();
    const newer = baseArtifact();
    newer.slate.fetchedAt = "2026-08-31T21:00:00.000Z";
    await promoteCanonicalArtifact(db, newer, opts());

    const older = baseArtifact();
    older.slate.fetchedAt = "2026-08-31T18:00:00.000Z";
    older.normalizedHash = "forced-restore-hash";
    const withoutForce = await promoteCanonicalArtifact(db, older, opts());
    expect(withoutForce.promoted).toBe(false);

    const withForce = await promoteCanonicalArtifact(db, older, opts({ force: true }));
    expect(withForce.promoted).toBe(true);
    const slateRow = getDb().prepare("SELECT fetched_at FROM slates WHERE provider_slate_id = '152904'").get() as { fetched_at: string };
    expect(slateRow.fetched_at).toBe("2026-08-31T18:00:00.000Z"); // explicit operator override took effect
  });

  it("transaction rollback: a failure mid-write leaves no partial slate (real DB, real BEGIN/COMMIT/ROLLBACK)", async () => {
    // Exercises the exact same db.transaction() primitive
    // promoteCanonicalArtifact itself uses, proving a failure partway
    // through a multi-statement write (slates succeeds, then a later
    // statement violates a real CHECK constraint) rolls back BOTH
    // statements, not just the failing one.
    const db = getExecutor();
    await expect(
      db.transaction(async (tx) => {
        await tx.run(
          "INSERT INTO slates (internal_slate_id, sport, site, provider, provider_slate_id, slate_date, first_game_start_utc, schema_version, created_at, updated_at) VALUES ('mid-tx','MLB','draftkings','draftkings_unofficial','999999','2026-08-31','2026-08-31T23:05:00Z','slate_normalized_v1','x','x')",
        );
        await tx.run(
          "INSERT INTO slate_players (internal_slate_id, provider_player_id, name, team, salary, identity_status, created_at, updated_at) VALUES ('mid-tx','1','A','BOS',4000,'NOT_A_REAL_STATUS','x','x')",
        );
      }),
    ).rejects.toThrow();

    const row = getDb().prepare("SELECT * FROM slates WHERE internal_slate_id = 'mid-tx'").get();
    expect(row).toBeUndefined(); // the slates insert was rolled back too, even though it succeeded on its own
  });

  describe("M7C: re-promotion preserves research-derived eligibility state", () => {
    it("a re-promotion with genuinely changed salary data does NOT wipe an already-computed eligibility_computed_at/eligibility_status/optimizer_eligible/game_id for a player still present", async () => {
      const db = getExecutor();
      const first = await promoteCanonicalArtifact(db, baseArtifact(), opts());
      expect(first.promoted).toBe(true);

      // Simulate the SEPARATE eligibility bridge (canonicalEligibility.ts)
      // having already computed and persisted real research-derived state.
      getDb()
        .prepare(
          "UPDATE slate_players SET eligibility_status = 'STARTING_HITTER', optimizer_eligible = 1, batting_order = 3, game_id = 'g1', eligibility_computed_at = 'x' WHERE internal_slate_id = ? AND provider_player_id = '999'",
        )
        .run(first.internalSlateId!);

      // A real, unrelated ACQUISITION change (salary correction) re-promotes.
      const resalaried = baseArtifact();
      resalaried.players[0].salary = 5200;
      resalaried.normalizedHash = "norm-hash-resalaried";
      resalaried.slate.fetchedAt = "2026-08-31T22:00:00.000Z";
      const second = await promoteCanonicalArtifact(db, resalaried, opts());
      expect(second.promoted).toBe(true);
      expect(second.internalSlateId).toBe(first.internalSlateId);

      const row = getDb().prepare("SELECT * FROM slate_players WHERE internal_slate_id = ? AND provider_player_id = '999'").get(first.internalSlateId!) as Record<string, unknown>;
      expect(row.salary).toBe(5200); // acquisition truth DID update
      expect(row.eligibility_status).toBe("STARTING_HITTER"); // research truth was PRESERVED
      expect(row.optimizer_eligible).toBe(1);
      expect(row.batting_order).toBe(3);
      expect(row.game_id).toBe("g1");
      expect(row.eligibility_computed_at).toBe("x");
    });

    it("a real player removal (no longer in the new artifact) still deletes that row, eligibility included", async () => {
      const db = getExecutor();
      const first = await promoteCanonicalArtifact(db, baseArtifact(), opts());
      getDb()
        .prepare("UPDATE slate_players SET eligibility_status = 'BENCH', optimizer_eligible = 0, eligibility_computed_at = 'x' WHERE internal_slate_id = ? AND provider_player_id = '999'")
        .run(first.internalSlateId!);

      const withoutPlayer = baseArtifact();
      withoutPlayer.players = [];
      withoutPlayer.identityMatches = {};
      withoutPlayer.normalizedHash = "norm-hash-no-players";
      withoutPlayer.slate.fetchedAt = "2026-08-31T22:00:00.000Z";
      await promoteCanonicalArtifact(db, withoutPlayer, opts());

      const count = (getDb().prepare("SELECT COUNT(*) as c FROM slate_players WHERE internal_slate_id = ?").get(first.internalSlateId!) as { c: number }).c;
      expect(count).toBe(0); // genuinely removed, not orphaned
    });

    it("a genuinely NEW player added on re-promotion starts with eligibility un-computed (never inherits another player's state)", async () => {
      const db = getExecutor();
      const first = await promoteCanonicalArtifact(db, baseArtifact(), opts());
      getDb()
        .prepare("UPDATE slate_players SET eligibility_status = 'STARTING_HITTER', optimizer_eligible = 1, eligibility_computed_at = 'x' WHERE internal_slate_id = ? AND provider_player_id = '999'")
        .run(first.internalSlateId!);

      const withNewPlayer = baseArtifact();
      withNewPlayer.players.push({
        internalSlateId: "proposed-uuid-1", internalPlayerId: null, providerPlayerId: "new-1",
        providerDraftableIds: [], name: "New Player", team: "TOR", opponent: "BOS",
        gameId: null, salary: 3500, positionEligibility: ["OF"], rosterSlotEligibility: [], identityStatus: "UNRESOLVED",
      });
      withNewPlayer.identityMatches["new-1"] = { identityStatus: "UNRESOLVED", matchMethod: null, matchConfidence: null, externalIdHints: [], candidateMlbPlayerIds: [], reason: null };
      withNewPlayer.normalizedHash = "norm-hash-new-player";
      withNewPlayer.slate.fetchedAt = "2026-08-31T22:00:00.000Z";
      await promoteCanonicalArtifact(db, withNewPlayer, opts());

      const newRow = getDb().prepare("SELECT * FROM slate_players WHERE internal_slate_id = ? AND provider_player_id = 'new-1'").get(first.internalSlateId!) as Record<string, unknown>;
      expect(newRow.eligibility_status).toBeNull();
      expect(newRow.eligibility_computed_at).toBeNull();

      const existingRow = getDb().prepare("SELECT eligibility_status FROM slate_players WHERE internal_slate_id = ? AND provider_player_id = '999'").get(first.internalSlateId!) as Record<string, unknown>;
      expect(existingRow.eligibility_status).toBe("STARTING_HITTER"); // still preserved
    });
  });

  describe("M4E: slateDate immutability on reschedule", () => {
    it("a reschedule that shifts the computed slateDate does NOT move the stored slate_date", async () => {
      const db = getExecutor();
      const first = await promoteCanonicalArtifact(db, baseArtifact(), opts());
      expect(first.promoted).toBe(true);
      expect(first.slateDateImmutabilityHeld).toBeUndefined(); // brand-new row -- nothing to hold against

      const rescheduled = baseArtifact();
      rescheduled.slate.firstGameStartUtc = "2026-09-02T03:05:00Z"; // now the earliest EASTERN calendar date is 2026-09-01, not 2026-08-31
      rescheduled.slate.slateDate = "2026-09-01"; // as a real caller's own compute_slate_date_from_game_starts() would newly compute
      rescheduled.normalizedHash = "norm-hash-rescheduled";
      rescheduled.slate.fetchedAt = "2026-08-31T22:00:00.000Z";
      const second = await promoteCanonicalArtifact(db, rescheduled, opts());

      expect(second.promoted).toBe(true);
      expect(second.internalSlateId).toBe(first.internalSlateId); // same canonical identity, never re-minted
      expect(second.slateDateImmutabilityHeld).toEqual({ storedSlateDate: "2026-08-31", incomingSlateDate: "2026-09-01" });

      const slateRow = getDb().prepare("SELECT slate_date FROM slates WHERE internal_slate_id = ?").get(first.internalSlateId!) as { slate_date: string };
      expect(slateRow.slate_date).toBe("2026-08-31"); // pinned to the FIRST assignment, never repartitioned

      const rows = getDb().prepare("SELECT COUNT(*) as c FROM slates WHERE provider_slate_id = '152904'").get() as { c: number };
      expect(rows.c).toBe(1); // no duplicate canonical slate created for the "new" date
    });

    it("a same-date time change (no calendar-day shift) reports no immutability event", async () => {
      const db = getExecutor();
      await promoteCanonicalArtifact(db, baseArtifact(), opts());

      const laterSameDay = baseArtifact();
      laterSameDay.slate.firstGameStartUtc = "2026-09-01T01:05:00Z"; // still 2026-08-31 Eastern
      laterSameDay.normalizedHash = "norm-hash-later-same-day";
      laterSameDay.slate.fetchedAt = "2026-08-31T22:00:00.000Z";
      const result = await promoteCanonicalArtifact(db, laterSameDay, opts());

      expect(result.promoted).toBe(true);
      expect(result.slateDateImmutabilityHeld).toBeUndefined();
    });

    it("immutability is held even for a semantic-duplicate no-op re-ingestion after a reschedule was already recorded", async () => {
      const db = getExecutor();
      const first = await promoteCanonicalArtifact(db, baseArtifact(), opts());

      const rescheduled = baseArtifact();
      rescheduled.slate.slateDate = "2026-09-01";
      rescheduled.normalizedHash = "norm-hash-rescheduled";
      rescheduled.slate.fetchedAt = "2026-08-31T22:00:00.000Z";
      await promoteCanonicalArtifact(db, rescheduled, opts());

      // A repeat ingestion of the SAME rescheduled content (identical
      // normalizedHash) is a semantic no-op, but must still surface the
      // held immutability against the ORIGINAL stored slate_date.
      const repeat = baseArtifact();
      repeat.slate.slateDate = "2026-09-01";
      repeat.normalizedHash = "norm-hash-rescheduled";
      const result = await promoteCanonicalArtifact(db, repeat, opts());

      expect(result.promoted).toBe(false);
      expect(result.reason).toMatch(/no-op/);
      expect(result.slateDateImmutabilityHeld).toEqual({ storedSlateDate: "2026-08-31", incomingSlateDate: "2026-09-01" });
      expect(result.internalSlateId).toBe(first.internalSlateId);
    });
  });

  describe("M3I: verifyNormalizedHash (rehydration hardening)", () => {
    it("accepts a valid, untampered artifact", async () => {
      const db = getExecutor();
      const artifact = withRealHash(baseArtifact());
      const result = await promoteCanonicalArtifact(db, artifact, opts({ verifyNormalizedHash: true }));
      expect(result.promoted).toBe(true);
    });

    it("rejects a tampered artifact whose declared normalizedHash does not match its real content", async () => {
      const db = getExecutor();
      const artifact = baseArtifact();
      artifact.normalizedHash = "this-does-not-match-the-real-content-hash";
      const result = await promoteCanonicalArtifact(db, artifact, opts({ verifyNormalizedHash: true }));
      expect(result.promoted).toBe(false);
      expect(result.reason).toMatch(/tampered|corrupted/);
      const count = (getDb().prepare("SELECT COUNT(*) as c FROM slates").get() as { c: number }).c;
      expect(count).toBe(0);
    });

    it("--force does NOT bypass a hash-tamper rejection", async () => {
      const db = getExecutor();
      const artifact = baseArtifact();
      artifact.normalizedHash = "tampered-hash-value";
      const result = await promoteCanonicalArtifact(db, artifact, opts({ verifyNormalizedHash: true, force: true }));
      expect(result.promoted).toBe(false);
      expect(result.reason).toMatch(/tampered|corrupted/);
    });

    it("an unsupported schemaVersion is still rejected even when verifyNormalizedHash is requested", async () => {
      const db = getExecutor();
      const artifact = baseArtifact({ schemaVersion: "slate_normalized_v99" });
      const result = await promoteCanonicalArtifact(db, artifact, opts({ verifyNormalizedHash: true }));
      expect(result.promoted).toBe(false);
      expect(result.reason).toMatch(/Unknown schemaVersion/);
    });

    it("an older artifact is still rejected under verifyNormalizedHash (real content, just stale)", async () => {
      const db = getExecutor();
      const newer = withRealHash(baseArtifact());
      newer.slate.fetchedAt = "2026-08-31T21:00:00.000Z";
      newer.normalizedHash = computeNormalizedHash(newer.slate as unknown as Record<string, unknown>, newer.players as unknown as Array<Record<string, unknown>>);
      await promoteCanonicalArtifact(db, newer, opts());

      // Genuinely different content (not just a different fetchedAt,
      // which is excluded from the hash and would otherwise make this
      // indistinguishable from the identical-hash no-op case) so the
      // real, correctly-declared hash differs from `newer`'s.
      const older = baseArtifact();
      older.slate.fetchedAt = "2026-08-31T18:00:00.000Z";
      older.players[0].salary = 4600;
      older.normalizedHash = computeNormalizedHash(older.slate as unknown as Record<string, unknown>, older.players as unknown as Array<Record<string, unknown>>);
      const result = await promoteCanonicalArtifact(db, older, opts({ verifyNormalizedHash: true }));
      expect(result.promoted).toBe(false);
      expect(result.reason).toMatch(/older/);
    });
  });
});
