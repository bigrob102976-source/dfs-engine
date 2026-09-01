import { describe, expect, it } from "vitest";

import { computeNormalizedHash, computeRawHash, pyJsonStringify } from "../canonicalHashing";

// M3H -- cross-language golden fixtures. These hashes were computed
// ONCE by the real Python canonical/hashing.py::compute_normalized_hash
// (not re-derived here) -- see the generation command in this
// milestone's own report. If this test ever fails after a change to
// EITHER language's implementation, hash parity has broken; do not
// "fix" it by updating the expected value without re-verifying against
// the real Python function.

const GOLDEN_SLATE_1 = {
  internalSlateId: "uuid-1", sport: "MLB", site: "draftkings", provider: "draftkings_unofficial",
  providerSlateId: "152904", slateName: "Main", slateDate: "2026-08-31",
  firstGameStartUtc: "2026-08-31T23:05:00Z", gameCount: 2, gameIds: ["g2", "g1"],
  salaryCap: 50000, rosterTemplate: { OF: 3, P: 2 }, sourceProvenance: "DRAFTKINGS_UNOFFICIAL_LIVE",
  validationState: "VALID", validationFindings: [] as string[], fetchedAt: "2026-08-31T20:00:00Z",
};

const GOLDEN_PLAYERS_1 = [
  {
    internalSlateId: "uuid-1", internalPlayerId: null, providerPlayerId: "999", providerDraftableIds: ["102", "101"],
    name: "José Ramírez", team: "CLE", opponent: "BOS", gameId: "g1", salary: 5200,
    positionEligibility: ["OF", "1B"], rosterSlotEligibility: [] as string[], identityStatus: "UNRESOLVED",
  },
  {
    internalSlateId: "uuid-1", internalPlayerId: null, providerPlayerId: "555", providerDraftableIds: ["201"],
    name: "Flex Player", team: "BOS", opponent: "CLE", gameId: "g1", salary: 4000,
    positionEligibility: ["P"], rosterSlotEligibility: [] as string[], identityStatus: "RESOLVED",
  },
];

const GOLDEN_HASH_1 = "7122ee09477fb050aa7209dab410560b62386b00d1d51a5f4dcda39b1d1f2675";
const GOLDEN_HASH_2_EMPTY_PLAYERS = "50129d3870a9da66f88e09a2032d49037402652b872e92f63f64293fed0750e2";

describe("computeNormalizedHash -- Python/TypeScript parity (golden fixtures)", () => {
  it("matches the real Python hash for a two-player slate with a non-ASCII name", () => {
    expect(computeNormalizedHash(GOLDEN_SLATE_1, GOLDEN_PLAYERS_1)).toBe(GOLDEN_HASH_1);
  });

  it("matches the real Python hash for a slate with zero players", () => {
    const slate2 = { ...GOLDEN_SLATE_1, providerSlateId: "999999" };
    expect(computeNormalizedHash(slate2, [])).toBe(GOLDEN_HASH_2_EMPTY_PLAYERS);
  });
});

describe("computeNormalizedHash -- determinism and content sensitivity", () => {
  it("player reorder produces the same hash", () => {
    const reordered = [GOLDEN_PLAYERS_1[1], GOLDEN_PLAYERS_1[0]];
    expect(computeNormalizedHash(GOLDEN_SLATE_1, reordered)).toBe(computeNormalizedHash(GOLDEN_SLATE_1, GOLDEN_PLAYERS_1));
  });

  it("dict/map key reorder produces the same hash", () => {
    const reorderedSlate = Object.fromEntries(Object.entries(GOLDEN_SLATE_1).reverse());
    expect(computeNormalizedHash(reorderedSlate, GOLDEN_PLAYERS_1)).toBe(computeNormalizedHash(GOLDEN_SLATE_1, GOLDEN_PLAYERS_1));
  });

  it("fetchedAt change produces the same hash", () => {
    const changed = { ...GOLDEN_SLATE_1, fetchedAt: "2099-01-01T00:00:00Z" };
    expect(computeNormalizedHash(changed, GOLDEN_PLAYERS_1)).toBe(computeNormalizedHash(GOLDEN_SLATE_1, GOLDEN_PLAYERS_1));
  });

  it("internalSlateId change produces the same hash", () => {
    const changed = { ...GOLDEN_SLATE_1, internalSlateId: "totally-different-uuid" };
    expect(computeNormalizedHash(changed, GOLDEN_PLAYERS_1)).toBe(computeNormalizedHash(GOLDEN_SLATE_1, GOLDEN_PLAYERS_1));
  });

  it("internalPlayerId change produces the same hash", () => {
    const changed = [{ ...GOLDEN_PLAYERS_1[0], internalPlayerId: "some-uuid" }, GOLDEN_PLAYERS_1[1]];
    expect(computeNormalizedHash(GOLDEN_SLATE_1, changed)).toBe(computeNormalizedHash(GOLDEN_SLATE_1, GOLDEN_PLAYERS_1));
  });

  it("identityStatus change produces the same hash", () => {
    const changed = [{ ...GOLDEN_PLAYERS_1[0], identityStatus: "RESOLVED" }, GOLDEN_PLAYERS_1[1]];
    expect(computeNormalizedHash(GOLDEN_SLATE_1, changed)).toBe(computeNormalizedHash(GOLDEN_SLATE_1, GOLDEN_PLAYERS_1));
  });

  it("salary change produces a DIFFERENT hash", () => {
    const changed = [{ ...GOLDEN_PLAYERS_1[0], salary: 5300 }, GOLDEN_PLAYERS_1[1]];
    expect(computeNormalizedHash(GOLDEN_SLATE_1, changed)).not.toBe(computeNormalizedHash(GOLDEN_SLATE_1, GOLDEN_PLAYERS_1));
  });

  it("player membership change produces a DIFFERENT hash", () => {
    const changed = [...GOLDEN_PLAYERS_1, { ...GOLDEN_PLAYERS_1[0], providerPlayerId: "777" }];
    expect(computeNormalizedHash(GOLDEN_SLATE_1, changed)).not.toBe(computeNormalizedHash(GOLDEN_SLATE_1, GOLDEN_PLAYERS_1));
  });

  it("eligibility change produces a DIFFERENT hash", () => {
    const changed = [{ ...GOLDEN_PLAYERS_1[0], positionEligibility: ["OF"] }, GOLDEN_PLAYERS_1[1]];
    expect(computeNormalizedHash(GOLDEN_SLATE_1, changed)).not.toBe(computeNormalizedHash(GOLDEN_SLATE_1, GOLDEN_PLAYERS_1));
  });

  it("draftableId change produces a DIFFERENT hash", () => {
    const changed = [{ ...GOLDEN_PLAYERS_1[0], providerDraftableIds: ["101"] }, GOLDEN_PLAYERS_1[1]];
    expect(computeNormalizedHash(GOLDEN_SLATE_1, changed)).not.toBe(computeNormalizedHash(GOLDEN_SLATE_1, GOLDEN_PLAYERS_1));
  });

  it("DraftGroup/providerSlateId change produces a DIFFERENT hash", () => {
    const changed = { ...GOLDEN_SLATE_1, providerSlateId: "999999" };
    expect(computeNormalizedHash(changed, GOLDEN_PLAYERS_1)).not.toBe(computeNormalizedHash(GOLDEN_SLATE_1, GOLDEN_PLAYERS_1));
  });
});

describe("pyJsonStringify -- ensure_ascii-style escaping parity", () => {
  it("escapes non-ASCII characters as \\uXXXX, matching Python's ensure_ascii=True default", () => {
    expect(pyJsonStringify("José")).toBe('"Jos\\u00e9"');
  });

  it("recursively sorts object keys regardless of insertion order", () => {
    expect(pyJsonStringify({ b: 1, a: 2 })).toBe('{"a":2,"b":1}');
  });

  it("uses compact separators with no whitespace", () => {
    expect(pyJsonStringify({ a: [1, 2], b: "x" })).toBe('{"a":[1,2],"b":"x"}');
  });
});

describe("computeRawHash", () => {
  it("identical bytes produce the same hash", () => {
    const buf = Buffer.from('{"a":1}', "utf-8");
    expect(computeRawHash(buf)).toBe(computeRawHash(Buffer.from('{"a":1}', "utf-8")));
  });

  it("one byte difference produces a different hash", () => {
    expect(computeRawHash(Buffer.from('{"a":1}'))).not.toBe(computeRawHash(Buffer.from('{"a":2}')));
  });

  it("matches Python's compute_raw_hash for the same bytes (sha256 is a standard algorithm -- verified against a known vector)", () => {
    // SHA-256("") -- a standard, language-independent test vector.
    expect(computeRawHash(Buffer.from(""))).toBe("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  });
});
