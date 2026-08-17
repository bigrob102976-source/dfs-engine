import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "@/lib/db/client";
import { insertSubscription } from "@/lib/db/subscriptions";
import { createUser } from "@/lib/db/users";

import AdminOverviewPage from "../page";

beforeEach(() => {
  __resetDbForTests();
});

describe("AdminOverviewPage", () => {
  it("renders every required KPI card with real zeroed figures when the system is empty", async () => {
    render(await AdminOverviewPage());

    expect(screen.getByText("Total Users")).toBeInTheDocument();
    expect(screen.getByText("Active Members")).toBeInTheDocument();
    expect(screen.getByText("Active Trials")).toBeInTheDocument();
    expect(screen.getByText("Weekly Members")).toBeInTheDocument();
    expect(screen.getByText("Monthly Members")).toBeInTheDocument();
    expect(screen.getByText("Canceled Members")).toBeInTheDocument();
    expect(screen.getByText("Past Due")).toBeInTheDocument();
    expect(screen.getByText("Complimentary Accounts")).toBeInTheDocument();
    expect(screen.getByText("MRR")).toBeInTheDocument();
    expect(screen.getByText("Estimated ARR")).toBeInTheDocument();
    expect(screen.getByText("Trial Conversion")).toBeInTheDocument();

    // No payment processor connected, no subscribers yet -- real $0, not fabricated.
    expect(screen.getAllByText("$0.00").length).toBeGreaterThanOrEqual(2);
    // No one has ever trialed -- genuinely uncalculable, must show "--" not "0%".
    expect(screen.getByText("--")).toBeInTheDocument();
  });

  it("reflects a real active subscriber in the Active Members and MRR cards", async () => {
    const user = createUser({ email: "kpi@example.com", passwordHash: "h" });
    insertSubscription({ userId: user.id, planId: "monthly", status: "active" });

    render(await AdminOverviewPage());

    const activeMembersCard = screen.getByText("Active Members").closest("div");
    expect(activeMembersCard?.parentElement?.textContent).toContain("1");
    expect(screen.getByText("$29.99")).toBeInTheDocument();
  });
});
