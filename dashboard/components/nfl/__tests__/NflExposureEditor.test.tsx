import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { NflExposureEditor } from "../NflExposureEditor";
import { loadExposureState, saveExposureState } from "@/lib/nfl/exposureStorage";
import type { NflPlayerRow } from "@/lib/nfl/types";

function player(overrides: Partial<NflPlayerRow>): NflPlayerRow {
  return {
    draftkings_player_id: "1", name: "Test Player", position: "WR", team: "BUF", opponent: "MIA", game_id: "100",
    salary: 6000, roster_slots: ["WR", "FLEX"], is_team_entity: false, status: null, injury_status: null,
    gsis_id: null, identity_resolved: true, usage: null, projection: null, ownership: null, matchup: null,
    ...overrides,
  };
}

beforeEach(() => {
  window.localStorage.clear();
});

describe("NflExposureEditor (NFL M13)", () => {
  it("shows an empty state when no overrides are set", () => {
    render(<NflExposureEditor players={[player({})]} draftGroupId={151307} />);
    expect(screen.getByText(/No per-player exposure overrides set/)).toBeInTheDocument();
  });

  it("searching and clicking a result adds a max-exposure override and persists it", () => {
    render(<NflExposureEditor players={[player({ draftkings_player_id: "1", name: "Zay Flowers" })]} draftGroupId={151307} />);
    fireEvent.change(screen.getByPlaceholderText(/Search a player/), { target: { value: "Zay" } });
    fireEvent.click(screen.getByText(/Zay Flowers/));
    expect(screen.queryByText(/No per-player exposure overrides set/)).not.toBeInTheDocument();
    expect(loadExposureState(151307).maxExposure["1"]).toBe(0.5); // default add value
  });

  it("existing overrides render editable Min/Max inputs seeded from storage", () => {
    saveExposureState(151307, { maxExposure: { "1": 0.25 }, minExposure: { "1": 0.1 } });
    render(<NflExposureEditor players={[player({ draftkings_player_id: "1", name: "Existing Override" })]} draftGroupId={151307} />);
    expect(screen.getByText(/Existing Override/)).toBeInTheDocument();
    const inputs = screen.getAllByRole("spinbutton") as HTMLInputElement[];
    expect(inputs.map((i) => i.value)).toEqual(["10", "25"]);
  });

  it("editing the Max input updates and persists the fraction", () => {
    saveExposureState(151307, { maxExposure: { "1": 0.25 }, minExposure: {} });
    render(<NflExposureEditor players={[player({ draftkings_player_id: "1", name: "Existing Override" })]} draftGroupId={151307} />);
    const [, maxInput] = screen.getAllByRole("spinbutton") as HTMLInputElement[]; // [Min, Max] column order
    fireEvent.change(maxInput, { target: { value: "60" } });
    expect(loadExposureState(151307).maxExposure["1"]).toBe(0.6);
  });

  it("Remove clears both min and max exposure for that player", () => {
    saveExposureState(151307, { maxExposure: { "1": 0.5 }, minExposure: { "1": 0.2 } });
    render(<NflExposureEditor players={[player({ draftkings_player_id: "1", name: "Existing Override" })]} draftGroupId={151307} />);
    fireEvent.click(screen.getByText("Remove"));
    expect(loadExposureState(151307)).toEqual({ maxExposure: {}, minExposure: {} });
    expect(screen.getByText(/No per-player exposure overrides set/)).toBeInTheDocument();
  });

  it("search requires at least 2 characters before showing results", () => {
    render(<NflExposureEditor players={[player({ draftkings_player_id: "1", name: "Zay Flowers" })]} draftGroupId={151307} />);
    fireEvent.change(screen.getByPlaceholderText(/Search a player/), { target: { value: "Z" } });
    expect(screen.queryByText(/Zay Flowers/)).not.toBeInTheDocument();
  });
});
