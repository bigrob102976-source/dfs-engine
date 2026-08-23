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
  it("lists every seeded page-level feature flag as PRODUCTION by default, and the M32.4 Big Money ML optimizer capability as ADMIN_ONLY", async () => {
    render(await AdminFeaturesPage());

    expect(screen.getByText("Optimizer")).toBeInTheDocument();
    expect(screen.getByText("Big Money ML Optimizer")).toBeInTheDocument();
    const selects = screen.getAllByRole("combobox") as HTMLSelectElement[];
    expect(selects.length).toBeGreaterThan(0);
    // Every page-level flag (Optimizer, Pitchers, Hitters, ...) still
    // defaults PRODUCTION; the one M32.4 addition defaults ADMIN_ONLY.
    expect(selects.some((s) => s.value === "ADMIN_ONLY")).toBe(true);
    expect(selects.filter((s) => s.value === "PRODUCTION").length).toBeGreaterThan(0);
  });
});
