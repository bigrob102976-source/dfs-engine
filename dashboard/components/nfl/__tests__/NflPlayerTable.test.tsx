import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NflPlayerTable } from "../NflPlayerTable";
import type { NflPlayerRow } from "@/lib/nfl/types";

function player(overrides: Partial<NflPlayerRow>): NflPlayerRow {
  return {
    draftkings_player_id: "1",
    name: "Test Player",
    position: "WR",
    team: "BUF",
    opponent: "MIA",
    game_id: "100",
    salary: 6000,
    roster_slots: ["WR", "FLEX"],
    is_team_entity: false,
    status: null,
    injury_status: null,
    gsis_id: "00-0000001",
    identity_resolved: true,
    usage: null,
    projection: { projection: 12.5, floor: 8.0, ceiling: 20.0, source: "BIG_MONEY_NATIVE", model_name: "m", model_version: "v1" },
    ownership: null,
    matchup: null,
    status_info: { normalized_status: "ACTIVE", raw_status: null, excluded_by_default: false, warn: false },
    game_lock: null,
    ...overrides,
  };
}

describe("NflPlayerTable -- Ownership column (NFL M12)", () => {
  it("renders a real ownership percentage instead of a placeholder", () => {
    const rows = [player({ draftkings_player_id: "1", name: "Owned Guy", ownership: {
      ownership_projection: 18.4, ownership_rank: 1, ownership_tier: "high", chalk_score: 70, leverage_score: 5,
      ownership_confidence: 80, value: 20.8, flex_ownership_component: 3.1, source: "BIG_MONEY_NATIVE_OWNERSHIP_V1",
      method: "deterministic_estimator", model_version: "nfl_ownership_v1",
    } })];
    render(<NflPlayerTable players={rows} draftGroupId={151307} variant="players" />);
    expect(screen.getByText("18.4%")).toBeInTheDocument();
  });

  it("renders -- (never a fake 0%) when the player has no ownership estimate", () => {
    const rows = [player({ draftkings_player_id: "2", name: "No Own Guy", ownership: null })];
    render(<NflPlayerTable players={rows} draftGroupId={151307} variant="players" />);
    const dashes = screen.getAllByText("--");
    expect(dashes.length).toBeGreaterThan(0);
  });

  it("shows the Ownership column on the projections variant too", () => {
    const rows = [player({ draftkings_player_id: "1", ownership: {
      ownership_projection: 9.9, ownership_rank: 5, ownership_tier: "medium", chalk_score: 40, leverage_score: 1,
      ownership_confidence: 60, value: 15.0, flex_ownership_component: 1.0, source: "BIG_MONEY_NATIVE_OWNERSHIP_V1",
      method: "deterministic_estimator", model_version: "nfl_ownership_v1",
    } })];
    render(<NflPlayerTable players={rows} draftGroupId={151307} variant="projections" />);
    expect(screen.getByText("Ownership")).toBeInTheDocument();
    expect(screen.getByText("9.9%")).toBeInTheDocument();
  });

  it("sorts numerically by ownership, descending on first click, with missing ownership always last", () => {
    const rows = [
      player({ draftkings_player_id: "a", name: "Low Owned", ownership: { ownership_projection: 2.0, ownership_rank: 3, ownership_tier: "low", chalk_score: 10, leverage_score: 0, ownership_confidence: 50, value: 10, flex_ownership_component: 0.5, source: "BIG_MONEY_NATIVE_OWNERSHIP_V1", method: "deterministic_estimator", model_version: "nfl_ownership_v1" } }),
      player({ draftkings_player_id: "b", name: "High Owned", ownership: { ownership_projection: 25.0, ownership_rank: 1, ownership_tier: "very_high", chalk_score: 90, leverage_score: 10, ownership_confidence: 90, value: 30, flex_ownership_component: 5, source: "BIG_MONEY_NATIVE_OWNERSHIP_V1", method: "deterministic_estimator", model_version: "nfl_ownership_v1" } }),
      player({ draftkings_player_id: "c", name: "No Own", ownership: null }),
    ];
    render(<NflPlayerTable players={rows} draftGroupId={151307} variant="players" />);

    fireEvent.click(screen.getByText("Ownership", { selector: "button" }));

    const rowsInOrder = screen.getAllByRole("row").slice(1); // skip header row
    const namesInOrder = rowsInOrder.map((r) => r.textContent);
    // High Owned (25%) should render before Low Owned (2%), and No Own
    // (null) should sort last regardless of direction.
    const highIdx = namesInOrder.findIndex((t) => t?.includes("High Owned"));
    const lowIdx = namesInOrder.findIndex((t) => t?.includes("Low Owned"));
    const noneIdx = namesInOrder.findIndex((t) => t?.includes("No Own"));
    expect(highIdx).toBeLessThan(lowIdx);
    expect(lowIdx).toBeLessThan(noneIdx);
  });
});

describe("NflPlayerTable -- real status badge (NFL M14)", () => {
  it("shows no badge at all for an ACTIVE player -- never a fabricated green badge", () => {
    const rows = [player({ name: "Healthy Guy", status_info: { normalized_status: "ACTIVE", raw_status: "None", excluded_by_default: false, warn: false } })];
    render(<NflPlayerTable players={rows} draftGroupId={151307} variant="players" />);
    expect(screen.queryByText("ACTIVE")).not.toBeInTheDocument();
  });

  it("shows a Q badge for QUESTIONABLE", () => {
    const rows = [player({ name: "Q Guy", status_info: { normalized_status: "QUESTIONABLE", raw_status: "Q", excluded_by_default: false, warn: true } })];
    render(<NflPlayerTable players={rows} draftGroupId={151307} variant="players" />);
    expect(screen.getByText("Q")).toBeInTheDocument();
  });

  it("shows an OUT badge for OUT", () => {
    const rows = [player({ name: "Out Guy", status_info: { normalized_status: "OUT", raw_status: "OUT", excluded_by_default: true, warn: false } })];
    render(<NflPlayerTable players={rows} draftGroupId={151307} variant="players" />);
    expect(screen.getByText("OUT")).toBeInTheDocument();
  });
});
