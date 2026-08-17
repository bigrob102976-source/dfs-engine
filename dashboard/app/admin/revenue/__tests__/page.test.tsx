import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "@/lib/db/client";

import AdminRevenuePage from "../page";

beforeEach(() => {
  __resetDbForTests();
});

describe("AdminRevenuePage", () => {
  it("shows -- for Refunds and Churn Rate, never a fabricated number", async () => {
    render(await AdminRevenuePage());

    expect(screen.getByText("Refunds")).toBeInTheDocument();
    expect(screen.getByText("Churn Rate")).toBeInTheDocument();
    // A third "--" is expected too: Trial Conversion is also genuinely
    // uncalculable (0/0) on an empty system, not just Refunds/Churn.
    const dashes = screen.getAllByText("--");
    expect(dashes.length).toBe(3);
    expect(screen.getByText(/does not yet track payment refunds/)).toBeInTheDocument();
  });
});
