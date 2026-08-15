import { describe, expect, it } from "vitest";

import type { AiPlayerProjection } from "../aiProjections";
import {
  buildAiStackSummaries,
  highestAiConfidence,
  joinAiProjections,
  largestAiDowngrades,
  largestAiUpgrades,
  lowestAiConfidence,
  topAiValues,
  type AiRankedPlayer,
} from "../commandCenter";
import type { PlayerRow } from "../types";

function playerRow(overrides: Partial<PlayerRow> = {}): PlayerRow {
  return {
    id: "p1", playerType: "hitter", name: "Test Player", team: "DET", opponent: "CLE", gameId: "824238",
    position: "OF", positions: ["OF"], battingOrder: 1, salary: 4000, projection: 10, ceiling: 18, floor: 4,
    overall: 60, power: 60, matchup: 60, risk: 30, confidence: 80, ownership: 15, ownershipTier: "mid",
    chalkScore: 50, leverage: 5, tags: [], reasons: [], raw: { snapshot: {}, ownership: null, pool: null },
    ...overrides,
  };
}

function aiPlayer(overrides: Partial<AiPlayerProjection> = {}): AiPlayerProjection {
  return {
    player_id: "p1", name: "Test Player", team: "DET", player_type: "hitter", opponent: "CLE", game_id: "824238",
    salary: 4000, independent_projection: 10, independent_ceiling: 18, independent_floor: 4,
    external_projection: null, adjusted_projection: null,
    ai_projection: 12, ai_ceiling: 20, ai_floor: 5, ai_confidence: 85, ai_risk: 30, ai_grade: "B+", ai_value_score: 3,
    total_adjustment: 2, total_adjustment_percent: 20, adjustment_capped: false,
    signals: [], reasons: [], ai_summary: "summary", model_version: "0.1.0",
    ...overrides,
  };
}

function aiRow(overrides: Partial<AiRankedPlayer> = {}): AiRankedPlayer {
  return { ...playerRow(overrides), aiProjection: null, aiDelta: null, aiConfidence: null, aiRisk: null, aiGrade: null, ...overrides };
}

describe("joinAiProjections", () => {
  it("joins by player id, leaving AI fields null for unmatched players", () => {
    const rows = [playerRow({ id: "p1" }), playerRow({ id: "p2", name: "Unmatched" })];
    const map = new Map([["p1", aiPlayer({ player_id: "p1" })]]);
    const joined = joinAiProjections(rows, map);

    expect(joined[0].aiProjection).toBe(12);
    expect(joined[0].aiDelta).toBe(2);
    expect(joined[0].aiConfidence).toBe(85);
    expect(joined[0].aiGrade).toBe("B+");
    expect(joined[1].aiProjection).toBeNull();
    expect(joined[1].aiGrade).toBeNull();
  });

  it("never mutates the original PlayerRow", () => {
    const original = playerRow({ id: "p1" });
    joinAiProjections([original], new Map([["p1", aiPlayer()]]));
    expect((original as Partial<AiRankedPlayer>).aiProjection).toBeUndefined();
  });
});

describe("topAiValues", () => {
  it("ranks by AI projection per $1,000 salary, descending", () => {
    const cheap = aiRow({ id: "cheap", aiProjection: 10, salary: 2000 }); // 5.0
    const expensive = aiRow({ id: "expensive", aiProjection: 15, salary: 10000 }); // 1.5
    const ranked = topAiValues([expensive, cheap]);
    expect(ranked.map((r) => r.id)).toEqual(["cheap", "expensive"]);
    expect(ranked[0].aiValue).toBeCloseTo(5, 5);
  });

  it("excludes players with no AI projection or salary", () => {
    const noAi = aiRow({ id: "no-ai", aiProjection: null });
    const noSalary = aiRow({ id: "no-salary", aiProjection: 10, salary: null });
    expect(topAiValues([noAi, noSalary])).toEqual([]);
  });

  it("respects the limit", () => {
    const rows = Array.from({ length: 15 }, (_, i) => aiRow({ id: `p${i}`, aiProjection: i + 1, salary: 1000 }));
    expect(topAiValues(rows, 5)).toHaveLength(5);
  });
});

describe("largestAiUpgrades / largestAiDowngrades", () => {
  it("upgrades: only positive deltas, largest first", () => {
    const rows = [aiRow({ id: "a", aiDelta: 0.5 }), aiRow({ id: "b", aiDelta: 2.0 }), aiRow({ id: "c", aiDelta: -1.0 }), aiRow({ id: "d", aiDelta: null })];
    expect(largestAiUpgrades(rows).map((r) => r.id)).toEqual(["b", "a"]);
  });

  it("downgrades: only negative deltas, most negative first", () => {
    const rows = [aiRow({ id: "a", aiDelta: -0.5 }), aiRow({ id: "b", aiDelta: -2.0 }), aiRow({ id: "c", aiDelta: 1.0 })];
    expect(largestAiDowngrades(rows).map((r) => r.id)).toEqual(["b", "a"]);
  });

  it("zero delta appears in neither list", () => {
    const rows = [aiRow({ id: "zero", aiDelta: 0 })];
    expect(largestAiUpgrades(rows)).toEqual([]);
    expect(largestAiDowngrades(rows)).toEqual([]);
  });
});

describe("highestAiConfidence / lowestAiConfidence", () => {
  it("sorts descending / ascending, excluding nulls", () => {
    const rows = [aiRow({ id: "a", aiConfidence: 60 }), aiRow({ id: "b", aiConfidence: 95 }), aiRow({ id: "c", aiConfidence: null })];
    expect(highestAiConfidence(rows).map((r) => r.id)).toEqual(["b", "a"]);
    expect(lowestAiConfidence(rows).map((r) => r.id)).toEqual(["a", "b"]);
  });
});

describe("buildAiStackSummaries", () => {
  it("reuses buildStackSummaries by substituting projection with aiProjection", () => {
    const rows = [
      aiRow({ id: "h1", team: "DET", aiProjection: 20, projection: 5 }),
      aiRow({ id: "h2", team: "DET", aiProjection: 10, projection: 5 }),
      aiRow({ id: "h3", team: "CLE", aiProjection: 5, projection: 50 }), // independent projection ignored
    ];
    const summaries = buildAiStackSummaries(rows, {});
    const det = summaries.find((s) => s.team === "DET")!;
    const cle = summaries.find((s) => s.team === "CLE")!;
    expect(det.averageProjection).toBe(15); // (20+10)/2, from AI projections
    expect(cle.averageProjection).toBe(5); // from AI projection, NOT the independent 50
  });

  it("empty input returns empty array", () => {
    expect(buildAiStackSummaries([], {})).toEqual([]);
  });
});
