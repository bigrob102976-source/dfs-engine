import { beforeEach, describe, expect, it } from "vitest";

import { loadWorkspaceState, saveWorkspaceState, type PersistedWorkspaceState } from "../workspaceStorage";

const BASE: PersistedWorkspaceState = {
  selectedSlateId: "dkunofficial-152400",
  selectedDate: "2026-08-21",
  locks: [],
  exclusions: [],
  maxExposure: {},
  stackSize: null,
  stackTeam: null,
  allowPitcherVsHitter: false,
  minSalary: null,
  minUnique: 2,
  lineups: 20,
  objective: "projection",
};

beforeEach(() => {
  window.localStorage.clear();
});

describe("workspaceStorage -- Milestone 31.2C selectedDate persistence", () => {
  it("round-trips selectedSlateId and selectedDate together", () => {
    saveWorkspaceState(BASE);
    const loaded = loadWorkspaceState();
    expect(loaded?.selectedSlateId).toBe("dkunofficial-152400");
    expect(loaded?.selectedDate).toBe("2026-08-21");
  });

  it("selectedDate is optional -- state persisted before Milestone 31.2C still loads cleanly", () => {
    const legacy = { ...BASE } as Record<string, unknown>;
    delete legacy.selectedDate;
    window.localStorage.setItem("mlb-dfs-optimizer-workspace-v1", JSON.stringify(legacy));
    const loaded = loadWorkspaceState();
    expect(loaded?.selectedSlateId).toBe("dkunofficial-152400");
    expect(loaded?.selectedDate).toBeUndefined();
  });

  it("a null selectedDate (explicitly cleared back to 'no date selected') persists as null, not dropped", () => {
    saveWorkspaceState({ ...BASE, selectedDate: null });
    const loaded = loadWorkspaceState();
    expect(loaded?.selectedDate).toBeNull();
  });
});

describe("T1C: canonicalTestMode persistence", () => {
  it("round-trips canonicalTestMode", () => {
    saveWorkspaceState({ ...BASE, canonicalTestMode: true });
    expect(loadWorkspaceState()?.canonicalTestMode).toBe(true);
  });

  it("is optional -- state persisted before T1 still loads cleanly (absent means legacy, unchanged from before)", () => {
    window.localStorage.setItem("mlb-dfs-optimizer-workspace-v1", JSON.stringify(BASE));
    expect(loadWorkspaceState()?.canonicalTestMode).toBeUndefined();
  });
});
