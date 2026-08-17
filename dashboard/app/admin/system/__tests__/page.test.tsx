import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockExternalStatus = vi.fn();
const mockGameEnvStatus = vi.fn();
const mockMockMode = vi.fn();

vi.mock("@/lib/externalProjectionsStatus", () => ({
  getExternalProjectionsStatus: (...args: unknown[]) => mockExternalStatus(...args),
}));
vi.mock("@/lib/gameEnvironmentStatus", () => ({
  getGameEnvironmentStatus: (...args: unknown[]) => mockGameEnvStatus(...args),
}));
vi.mock("@/lib/mockMode", () => ({
  getMockModeEnabled: () => mockMockMode(),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { createUser } = await import("@/lib/db/users");

const AdminSystemPage = (await import("../page")).default;

beforeEach(() => {
  __resetDbForTests();
  mockExternalStatus.mockResolvedValue({ error: "no python configured in test env" });
  mockGameEnvStatus.mockResolvedValue({ error: "no python configured in test env" });
  mockMockMode.mockResolvedValue(false);
});

describe("AdminSystemPage", () => {
  it("shows real DB counts alongside provider status", async () => {
    createUser({ email: "sys@example.com", passwordHash: "h" });

    render(await AdminSystemPage());

    expect(screen.getByText("Total Users")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("DISABLED")).toBeInTheDocument();
  });

  it("shows the underlying error text rather than fabricating a status when a provider check fails", async () => {
    render(await AdminSystemPage());
    expect(screen.getAllByText("no python configured in test env").length).toBe(2);
  });

  it("shows ENABLED when mock mode is on", async () => {
    mockMockMode.mockResolvedValue(true);
    render(await AdminSystemPage());
    expect(screen.getByText("ENABLED")).toBeInTheDocument();
  });

  it("shows Stripe as not configured with the missing var names, and no failed webhooks yet", async () => {
    render(await AdminSystemPage());
    expect(screen.getByText("Stripe Webhooks")).toBeInTheDocument();
    expect(screen.getByText("Missing Configuration")).toBeInTheDocument();
    expect(screen.getByText("No failed webhook deliveries recorded.")).toBeInTheDocument();
  });

  it("shows real webhook status counts and recent failures, never a fabricated payload", async () => {
    const { claimWebhookEvent, markWebhookEventProcessed, markWebhookEventFailed } = await import("@/lib/db/stripeWebhookEvents");
    claimWebhookEvent("evt_ok", "customer.subscription.updated");
    markWebhookEventProcessed("evt_ok");
    claimWebhookEvent("evt_bad", "invoice.payment_failed");
    markWebhookEventFailed("evt_bad", "user not found for customer cus_x");

    render(await AdminSystemPage());
    expect(screen.getByText(/customer\.subscription\.updated/)).toBeInTheDocument();
    expect(screen.getByText(/user not found for customer cus_x/)).toBeInTheDocument();
  });
});
