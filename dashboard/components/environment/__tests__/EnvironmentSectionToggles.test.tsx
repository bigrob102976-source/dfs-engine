import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { EnvironmentSectionToggles } from "../EnvironmentSectionToggles";

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  window.localStorage.clear();
});

describe("EnvironmentSectionToggles", () => {
  it("renders a checkbox for each of the five toggleable sections, all on by default", async () => {
    render(<EnvironmentSectionToggles />);
    await act(async () => {});
    for (const label of ["Weather", "Vegas", "Bullpen", "Park", "Travel"]) {
      const checkbox = screen.getByLabelText(label) as HTMLInputElement;
      expect(checkbox.checked).toBe(true);
    }
  });

  it("persists a toggle to localStorage and reflects it back on next mount", async () => {
    const { unmount } = render(<EnvironmentSectionToggles />);
    await act(async () => {});
    fireEvent.click(screen.getByLabelText("Weather"));
    expect(JSON.parse(window.localStorage.getItem("bigmoney-environment-sections") ?? "{}").weather).toBe(false);
    unmount();

    render(<EnvironmentSectionToggles />);
    await act(async () => {});
    expect((screen.getByLabelText("Weather") as HTMLInputElement).checked).toBe(false);
  });
});
