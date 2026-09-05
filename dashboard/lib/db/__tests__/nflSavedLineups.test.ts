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
    expect(await getSavedLineupById("does-not-exist")).toBeNull();
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
    const updated = await updateSavedLineupSlots(row.id, JSON.stringify([{ roster_slot: "QB", draftkings_player_id: "2", name: "QB Two" }]));
    expect(updated!.id).toBe(row.id);
    expect(updated!.created_at).toBe(row.created_at);
    expect(JSON.parse(updated!.slots_json)[0].name).toBe("QB Two");
  });

  it("deleteSavedLineup only succeeds for the owning user", async () => {
    const uidA = await userId();
    const uidB = await userId();
    const row = await createSavedLineup({ userId: uidA, draftGroupId: DG_ID, slateDate: DATE, mode: "projection", stackConfigJson: "{}", slotsJson: slotsJson() });

    expect(await deleteSavedLineup(row.id, uidB)).toBe(false);
    expect(await getSavedLineupById(row.id)).not.toBeNull();

    expect(await deleteSavedLineup(row.id, uidA)).toBe(true);
    expect(await getSavedLineupById(row.id)).toBeNull();
  });
});
