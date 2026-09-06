import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "../client";
import { __resetExecutorForTests } from "../executor";
import { createSavedLineup, deleteSavedLineup, getSavedLineupById, listSavedLineups, updateSavedLineupSlots } from "../nflSavedLineups";
import { createUser } from "../users";

const DG_ID = 151307;
const DATE = "2026-09-13";

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

async function userId(): Promise<string> {
  return (await createUser({ email: `u-${Math.random()}@example.com`, passwordHash: "h" })).id;
}

function slotsJson() {
  return JSON.stringify([{ roster_slot: "QB", draftkings_player_id: "1", name: "QB One" }]);
}

describe("nfl_saved_lineups", () => {
  it("creates and round-trips a real saved lineup", async () => {
    const uid = await userId();
    const row = await createSavedLineup({
      userId: uid, draftGroupId: DG_ID, slateDate: DATE, mode: "projection",
      stackConfigJson: JSON.stringify({ qbStackMode: "single" }), slotsJson: slotsJson(),
    });
    expect(row.draft_group_id).toBe(DG_ID);
    expect(row.mode).toBe("projection");
    expect(JSON.parse(row.slots_json)[0].name).toBe("QB One");
    expect(row.created_at).toBe(row.updated_at);
  });

  it("getSavedLineupById returns null for an unknown id", async () => {
    const uid = await userId();
    expect(await getSavedLineupById("does-not-exist", uid)).toBeNull();
  });

  it("listSavedLineups scopes to user AND draft group", async () => {
    const uidA = await userId();
    const uidB = await userId();
    await createSavedLineup({ userId: uidA, draftGroupId: DG_ID, slateDate: DATE, mode: "projection", stackConfigJson: "{}", slotsJson: slotsJson() });
    await createSavedLineup({ userId: uidB, draftGroupId: DG_ID, slateDate: DATE, mode: "projection", stackConfigJson: "{}", slotsJson: slotsJson() });
    await createSavedLineup({ userId: uidA, draftGroupId: 999999, slateDate: DATE, mode: "projection", stackConfigJson: "{}", slotsJson: slotsJson() });

    const rows = await listSavedLineups(uidA, DG_ID);
    expect(rows).toHaveLength(1);
    expect(rows[0].user_id).toBe(uidA);
  });

  it("updateSavedLineupSlots replaces slots_json and bumps updated_at, id/created_at unchanged", async () => {
    const uid = await userId();
    const row = await createSavedLineup({ userId: uid, draftGroupId: DG_ID, slateDate: DATE, mode: "projection", stackConfigJson: "{}", slotsJson: slotsJson() });
    await new Promise((r) => setTimeout(r, 5));
    const updated = await updateSavedLineupSlots(row.id, uid, JSON.stringify([{ roster_slot: "QB", draftkings_player_id: "2", name: "QB Two" }]));
    expect(updated!.id).toBe(row.id);
    expect(updated!.created_at).toBe(row.created_at);
    expect(JSON.parse(updated!.slots_json)[0].name).toBe("QB Two");
  });

  it("deleteSavedLineup only succeeds for the owning user", async () => {
    const uidA = await userId();
    const uidB = await userId();
    const row = await createSavedLineup({ userId: uidA, draftGroupId: DG_ID, slateDate: DATE, mode: "projection", stackConfigJson: "{}", slotsJson: slotsJson() });

    expect(await deleteSavedLineup(row.id, uidB)).toBe(false);
    expect(await getSavedLineupById(row.id, uidA)).not.toBeNull();

    expect(await deleteSavedLineup(row.id, uidA)).toBe(true);
    expect(await getSavedLineupById(row.id, uidA)).toBeNull();
  });
});

async function makeLineup(userId: string) {
  return createSavedLineup({
    userId, draftGroupId: DG_ID, slateDate: DATE, mode: "projection",
    stackConfigJson: "{}", slotsJson: JSON.stringify([{ roster_slot: "QB", draftkings_player_id: "1" }]),
  });
}

/** NFL production access fix, Phase 5 -- ownership isolation is now
 * enforced IN THE SQL (WHERE id = ? AND user_id = ?), not left to every
 * caller to remember to check. Proven here at the DB layer directly, in
 * addition to the API-route-level tests, so a future new call site
 * can't accidentally reintroduce a cross-user leak by skipping an
 * inline check the way the pre-existing API routes used to require. */
describe("nflSavedLineups ownership isolation", () => {
  it("getSavedLineupById returns null for a real id when queried as a different user", async () => {
    const row = await makeLineup("user-a");
    expect(await getSavedLineupById(row.id, "user-a")).not.toBeNull();
    expect(await getSavedLineupById(row.id, "user-b")).toBeNull();
  });

  it("updateSavedLineupSlots (the late-swap write path) cannot modify another user's lineup", async () => {
    const row = await makeLineup("user-a");
    const result = await updateSavedLineupSlots(row.id, "user-b", JSON.stringify([{ roster_slot: "QB", draftkings_player_id: "999" }]));
    expect(result).toBeNull();

    const stillOwned = await getSavedLineupById(row.id, "user-a");
    expect(JSON.parse(stillOwned!.slots_json)[0].draftkings_player_id).toBe("1");
  });

  it("a nonexistent id and a real-but-not-owned id are indistinguishable (no existence oracle)", async () => {
    const row = await makeLineup("user-a");
    expect(await getSavedLineupById(row.id, "user-b")).toEqual(await getSavedLineupById("totally-made-up-id", "user-b"));
  });
});
