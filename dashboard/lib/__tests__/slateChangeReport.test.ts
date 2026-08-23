import { describe, expect, it } from "vitest";

import { diffSlateState, type SlateStateSnapshot } from "../slateChangeReport";

function state(overrides: Partial<SlateStateSnapshot> = {}): SlateStateSnapshot {
  return {
    teamsAwaitingLineups: [], confirmedHitters: 0, optimizerEligible: 0, startingPitcherIdByTeam: {},
    nativePlayerCount: 0, aiPlayerCount: 0, mlPlayerCount: 0, environmentGeneratedAt: null, blueCollarUpdated: null,
    ...overrides,
  };
}

describe("diffSlateState", () => {
  it("counts a team leaving teamsAwaitingLineups as one lineup posted", () => {
    const before = state({ teamsAwaitingLineups: ["PHI", "NYY"] });
    const after = state({ teamsAwaitingLineups: ["NYY"] });
    expect(diffSlateState(before, after).lineupsPosted).toBe(1);
  });

  it("counts multiple teams posting at once", () => {
    const before = state({ teamsAwaitingLineups: ["PHI", "NYY", "BOS"] });
    const after = state({ teamsAwaitingLineups: [] });
    expect(diffSlateState(before, after).lineupsPosted).toBe(3);
  });

  it("never reports a negative lineupsPosted when a team somehow reappears as awaiting", () => {
    const before = state({ teamsAwaitingLineups: [] });
    const after = state({ teamsAwaitingLineups: ["PHI"] });
    expect(diffSlateState(before, after).lineupsPosted).toBe(0);
  });

  it("computes hittersBecameEligible from the confirmedHitters delta, never negative", () => {
    expect(diffSlateState(state({ confirmedHitters: 0 }), state({ confirmedHitters: 18 })).hittersBecameEligible).toBe(18);
    expect(diffSlateState(state({ confirmedHitters: 18 }), state({ confirmedHitters: 10 })).hittersBecameEligible).toBe(0);
  });

  it("detects a starter change only when a team's starting pitcher id actually differs", () => {
    const before = state({ startingPitcherIdByTeam: { PHI: "p1", NYY: "p2" } });
    const after = state({ startingPitcherIdByTeam: { PHI: "p1", NYY: "p3" } });
    expect(diffSlateState(before, after).starterChanged).toBe(1);
  });

  it("does not count a team gaining a starter for the first time as a change", () => {
    const before = state({ startingPitcherIdByTeam: {} });
    const after = state({ startingPitcherIdByTeam: { PHI: "p1" } });
    expect(diffSlateState(before, after).starterChanged).toBe(0);
  });

  it("computes native/AI/ML generated counts from the player-count deltas", () => {
    const before = state({ nativePlayerCount: 29, aiPlayerCount: 29, mlPlayerCount: 15 });
    const after = state({ nativePlayerCount: 47, aiPlayerCount: 47, mlPlayerCount: 33 });
    const report = diffSlateState(before, after);
    expect(report.nativeGenerated).toBe(18);
    expect(report.aiGenerated).toBe(18);
    expect(report.mlGenerated).toBe(18);
  });

  it("stacksBecameReady coincides with lineupsPosted, by lib/stacks.ts's own CONFIRMED rule", () => {
    const before = state({ teamsAwaitingLineups: ["PHI", "NYY"] });
    const after = state({ teamsAwaitingLineups: [] });
    expect(diffSlateState(before, after).stacksBecameReady).toBe(2);
  });

  it("reports Vegas/Weather as unchanged when the environment report's generated_at is identical", () => {
    const before = state({ environmentGeneratedAt: "2026-08-23T18:00:00Z" });
    const after = state({ environmentGeneratedAt: "2026-08-23T18:00:00Z" });
    expect(diffSlateState(before, after).unchanged).toEqual(expect.arrayContaining(["Vegas", "Weather"]));
  });

  it("does not report Vegas/Weather as unchanged when generated_at moved", () => {
    const before = state({ environmentGeneratedAt: "2026-08-23T18:00:00Z" });
    const after = state({ environmentGeneratedAt: "2026-08-23T19:00:00Z" });
    expect(diffSlateState(before, after).unchanged).not.toContain("Vegas");
  });

  it("reports BlueCollar as unchanged when its own updated timestamp is identical", () => {
    const before = state({ blueCollarUpdated: "12:36 PM ET" });
    const after = state({ blueCollarUpdated: "12:36 PM ET" });
    expect(diffSlateState(before, after).unchanged).toContain("BlueCollar");
  });

  it("never reports a signal as unchanged when it was null before (nothing to compare against yet)", () => {
    const before = state({ environmentGeneratedAt: null, blueCollarUpdated: null });
    const after = state({ environmentGeneratedAt: null, blueCollarUpdated: null });
    expect(diffSlateState(before, after).unchanged).toEqual([]);
  });

  it("no-change refresh: every count is zero and every signal is reported unchanged", () => {
    const snapshot = state({
      teamsAwaitingLineups: ["PHI"], confirmedHitters: 5, environmentGeneratedAt: "t1", blueCollarUpdated: "b1",
    });
    const report = diffSlateState(snapshot, snapshot);
    expect(report.lineupsPosted).toBe(0);
    expect(report.hittersBecameEligible).toBe(0);
    expect(report.starterChanged).toBe(0);
    expect(report.nativeGenerated).toBe(0);
    expect(report.aiGenerated).toBe(0);
    expect(report.mlGenerated).toBe(0);
    expect(report.unchanged).toEqual(expect.arrayContaining(["Vegas", "Weather", "BlueCollar"]));
  });
});
