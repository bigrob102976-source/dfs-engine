import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const { __resetDbForTests } = await import("@/lib/db/client");

const AdminFeaturesPage = (await import("../page")).default;

beforeEach(() => {
  __resetDbForTests();
});

describe("AdminFeaturesPage", () => {
  it("lists every seeded feature flag, all PRODUCTION by default", async () => {
    render(await AdminFeaturesPage());

    expect(screen.getByText("Optimizer")).toBeInTheDocument();
    const selects = screen.getAllByRole("combobox") as HTMLSelectElement[];
    expect(selects.length).toBeGreaterThan(0);
    expect(selects.every((s) => s.value === "PRODUCTION")).toBe(true);
  });
});
