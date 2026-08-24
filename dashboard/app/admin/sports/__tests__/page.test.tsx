import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const { __resetDbForTests } = await import("@/lib/db/client");

const { __resetExecutorForTests } = await import("@/lib/db/executor");
const AdminSportsPage = (await import("../page")).default;

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

describe("AdminSportsPage", () => {
  it("shows MLB as LIVE and other sports as Coming Soon", async () => {
    render(await AdminSportsPage());

    expect(screen.getByText("MLB")).toBeInTheDocument();
    expect(screen.getByText("NFL")).toBeInTheDocument();
    expect(screen.getByText("NBA")).toBeInTheDocument();
    expect(screen.getByText("NHL")).toBeInTheDocument();

    const selects = screen.getAllByRole("combobox") as HTMLSelectElement[];
    expect(selects).toHaveLength(4);
    expect(selects[0].value).toBe("LIVE");
    expect(selects.slice(1).every((s) => s.value === "COMING_SOON")).toBe(true);
  });
});
