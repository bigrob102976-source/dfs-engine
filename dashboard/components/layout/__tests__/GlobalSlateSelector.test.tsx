import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mockPush = vi.fn();
let mockSearchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => "/dashboard/pitchers",
  useSearchParams: () => mockSearchParams,
}));

import { GlobalSlateSelector } from "../GlobalSlateSelector";
import type { SlateOption } from "@/lib/orchestrator/types";

function slate(overrides: Partial<SlateOption> = {}): SlateOption {
  return { slateId: "main", slateName: "Main", gameCount: 9, startTime: null, gameIds: ["g1"], playerCount: 142, ...overrides };
}

describe("GlobalSlateSelector", () => {
  it("shows an honest empty state when no slates are loaded", () => {
    render(<GlobalSlateSelector slates={[]} />);
    expect(screen.getByText("No DK slates loaded")).toBeInTheDocument();
  });

  it("always offers Full Day (All Games) as the first, default option", () => {
    mockSearchParams = new URLSearchParams();
    render(<GlobalSlateSelector slates={[slate()]} />);
    const select = screen.getByLabelText("Selected slate") as HTMLSelectElement;
    expect(select.value).toBe("");
    expect(screen.getByRole("option", { name: "Full Day (All Games)" })).toBeInTheDocument();
  });

  it("lists each slate with name and game count", () => {
    mockSearchParams = new URLSearchParams();
    render(<GlobalSlateSelector slates={[slate({ slateId: "main", slateName: "Main", gameCount: 9 }), slate({ slateId: "turbo", slateName: "Turbo", gameCount: 3 })]} />);
    expect(screen.getByRole("option", { name: "Main — 9 Games" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Turbo — 3 Games" })).toBeInTheDocument();
  });

  it("reflects the currently selected slate from the URL", () => {
    mockSearchParams = new URLSearchParams("slate=turbo");
    render(<GlobalSlateSelector slates={[slate({ slateId: "main" }), slate({ slateId: "turbo", slateName: "Turbo" })]} />);
    const select = screen.getByLabelText("Selected slate") as HTMLSelectElement;
    expect(select.value).toBe("turbo");
  });

  it("navigates to the same page with ?slate=<id> set, preserving other query params", () => {
    mockSearchParams = new URLSearchParams("player=123");
    render(<GlobalSlateSelector slates={[slate({ slateId: "main" }), slate({ slateId: "turbo", slateName: "Turbo" })]} />);
    fireEvent.change(screen.getByLabelText("Selected slate"), { target: { value: "turbo" } });
    expect(mockPush).toHaveBeenCalledWith("/dashboard/pitchers?player=123&slate=turbo");
  });

  it("clears the slate param when Full Day is re-selected", () => {
    mockSearchParams = new URLSearchParams("slate=turbo");
    render(<GlobalSlateSelector slates={[slate({ slateId: "turbo", slateName: "Turbo" })]} />);
    fireEvent.change(screen.getByLabelText("Selected slate"), { target: { value: "" } });
    expect(mockPush).toHaveBeenCalledWith("/dashboard/pitchers");
  });
});
