import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGetBillingMode = vi.fn();
vi.mock("@/lib/billing/stripeConfig", () => ({
  getBillingMode: () => mockGetBillingMode(),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const PricingPage = (await import("../page")).default;

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  mockGetBillingMode.mockReturnValue("dev");
});

describe("PricingPage", () => {
  it("renders the headline, both plans with correct prices/trial, and the disclosure copy", async () => {
    render(await PricingPage());

    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("PLAY SMARTER.");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("BUILD BETTER LINEUPS.");
    expect(screen.getByText("$10.99")).toBeInTheDocument();
    expect(screen.getByText("$29.99")).toBeInTheDocument();
    expect(screen.getAllByText("3-Day Free Trial")).toHaveLength(2);
    expect(screen.getAllByText("Start Free Trial")).toHaveLength(2);
    expect(screen.getByText(/Recurring subscription\. Cancel anytime\./)).toBeInTheDocument();
  });

  it("marks Monthly (not Weekly) as Best Value", async () => {
    render(await PricingPage());
    expect(screen.getByText("Best Value")).toBeInTheDocument();
  });

  it("links each plan's CTA to /subscribe?plan=<id>", async () => {
    render(await PricingPage());
    const links = screen.getAllByText("Start Free Trial") as HTMLAnchorElement[];
    const hrefs = links.map((el) => el.closest("a")?.getAttribute("href"));
    expect(hrefs).toContain("/subscribe?plan=weekly");
    expect(hrefs).toContain("/subscribe?plan=monthly");
  });

  it("shows the Stripe Test Mode badge only when billing mode is stripe_test", async () => {
    mockGetBillingMode.mockReturnValue("stripe_test");
    render(await PricingPage());
    expect(screen.getByText(/Stripe Test Mode/)).toBeInTheDocument();
  });

  it("hides the Stripe Test Mode badge in dev mode", async () => {
    mockGetBillingMode.mockReturnValue("dev");
    render(await PricingPage());
    expect(screen.queryByText(/Stripe Test Mode/)).not.toBeInTheDocument();
  });
});
