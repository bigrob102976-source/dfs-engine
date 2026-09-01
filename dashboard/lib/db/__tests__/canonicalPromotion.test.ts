import { beforeEach, describe, expect, it } from "vitest";

import type { CanonicalSlateArtifactDocument } from "../canonicalArtifact";
import { promoteCanonicalArtifact } from "../canonicalPromotion";
import { __resetDbForTests, getDb } from "../client";
import { __resetExecutorForTests, getExecutor } from "../executor";

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

  it("rejects a REJECTED validationState without writing anything", async () => {
    const db = getExecutor();
    const artifact = baseArtifact();
    artifact.slate.validationState = "REJECTED";
    const result = await promoteCanonicalArtifact(db, artifact, opts());
    expect(result.promoted).toBe(false);
    const count = (getDb().prepare("SELECT COUNT(*) as c FROM slates").get() as { c: number }).c;
    expect(count).toBe(0);
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
});
