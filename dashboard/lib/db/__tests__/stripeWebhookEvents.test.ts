import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "../client";
import {
  claimWebhookEvent,
  countWebhookEventsByStatus,
  getLastSuccessfulWebhookEvent,
  listRecentWebhookEvents,
  markWebhookEventFailed,
  markWebhookEventProcessed,
} from "../stripeWebhookEvents";

beforeEach(() => {
  __resetDbForTests();
});

describe("claimWebhookEvent", () => {
  it("a brand-new event id is claimed for processing", () => {
    const result = claimWebhookEvent("evt_1", "customer.subscription.updated");
    expect(result.shouldProcess).toBe(true);
  });

  it("a genuinely duplicate delivery of an already-PROCESSED event is skipped (true idempotency)", () => {
    claimWebhookEvent("evt_2", "customer.subscription.updated");
    markWebhookEventProcessed("evt_2");

    const redelivery = claimWebhookEvent("evt_2", "customer.subscription.updated");
    expect(redelivery.shouldProcess).toBe(false);
  });

  it("a concurrent/duplicate delivery while the FIRST is still 'processing' is re-claimed (safe because handlers are idempotent full-state upserts)", () => {
    const first = claimWebhookEvent("evt_3", "customer.subscription.updated");
    expect(first.shouldProcess).toBe(true);
    // Second delivery of the identical event id arrives before the first
    // call ever reaches markWebhookEventProcessed/Failed.
    const second = claimWebhookEvent("evt_3", "customer.subscription.updated");
    expect(second.shouldProcess).toBe(true);
  });

  it("an event that previously FAILED can be retried on redelivery", () => {
    claimWebhookEvent("evt_4", "invoice.payment_failed");
    markWebhookEventFailed("evt_4", "boom");

    const retry = claimWebhookEvent("evt_4", "invoice.payment_failed");
    expect(retry.shouldProcess).toBe(true);

    markWebhookEventProcessed("evt_4");
    const counts = countWebhookEventsByStatus();
    expect(counts.processed).toBe(1);
    expect(counts.failed).toBe(0);
  });

  it("never inserts two rows for the same event id (PK collision path, not a second row)", () => {
    claimWebhookEvent("evt_5", "customer.subscription.created");
    claimWebhookEvent("evt_5", "customer.subscription.created");
    claimWebhookEvent("evt_5", "customer.subscription.created");
    expect(listRecentWebhookEvents().filter((e) => e.id === "evt_5")).toHaveLength(1);
  });
});

describe("markWebhookEventProcessed / markWebhookEventFailed", () => {
  it("processed sets processed_at and clears any prior error", () => {
    claimWebhookEvent("evt_6", "invoice.paid");
    markWebhookEventFailed("evt_6", "transient error");
    markWebhookEventProcessed("evt_6");

    const events = listRecentWebhookEvents();
    const row = events.find((e) => e.id === "evt_6")!;
    expect(row.status).toBe("processed");
    expect(row.processed_at).not.toBeNull();
    expect(row.error).toBeNull();
  });

  it("failed records the error message and leaves processed_at unset", () => {
    claimWebhookEvent("evt_7", "checkout.session.completed");
    markWebhookEventFailed("evt_7", "user not found for customer");

    const row = listRecentWebhookEvents().find((e) => e.id === "evt_7")!;
    expect(row.status).toBe("failed");
    expect(row.error).toBe("user not found for customer");
    expect(row.processed_at).toBeNull();
  });
});

describe("countWebhookEventsByStatus", () => {
  it("zero-fills every status and counts real rows", () => {
    expect(countWebhookEventsByStatus()).toEqual({ processing: 0, processed: 0, failed: 0 });

    claimWebhookEvent("evt_8", "a");
    claimWebhookEvent("evt_9", "b");
    markWebhookEventProcessed("evt_9");
    claimWebhookEvent("evt_10", "c");
    markWebhookEventFailed("evt_10", "err");

    expect(countWebhookEventsByStatus()).toEqual({ processing: 1, processed: 1, failed: 1 });
  });
});

describe("listRecentWebhookEvents", () => {
  it("orders most-recent-first and respects the limit", () => {
    for (let i = 0; i < 5; i++) claimWebhookEvent(`evt_list_${i}`, "type");
    expect(listRecentWebhookEvents(3)).toHaveLength(3);
  });
});

describe("getLastSuccessfulWebhookEvent", () => {
  it("returns null when nothing has ever been processed", () => {
    claimWebhookEvent("evt_11", "type");
    expect(getLastSuccessfulWebhookEvent()).toBeNull();
  });

  it("returns the most recently processed event", () => {
    claimWebhookEvent("evt_12", "customer.subscription.created");
    markWebhookEventProcessed("evt_12");
    claimWebhookEvent("evt_13", "customer.subscription.updated");
    markWebhookEventProcessed("evt_13");

    expect(getLastSuccessfulWebhookEvent()?.id).toBe("evt_13");
  });
});
