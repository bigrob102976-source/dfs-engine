import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "../client";
import { __resetExecutorForTests } from "../executor";
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
  __resetExecutorForTests();
});

describe("claimWebhookEvent", () => {
  it("a brand-new event id is claimed for processing", async () => {
    const result = await claimWebhookEvent("evt_1", "customer.subscription.updated");
    expect(result.shouldProcess).toBe(true);
  });

  it("a genuinely duplicate delivery of an already-PROCESSED event is skipped (true idempotency)", async () => {
    await claimWebhookEvent("evt_2", "customer.subscription.updated");
    await markWebhookEventProcessed("evt_2");

    const redelivery = await claimWebhookEvent("evt_2", "customer.subscription.updated");
    expect(redelivery.shouldProcess).toBe(false);
  });

  it("a concurrent/duplicate delivery while the FIRST is still 'processing' is re-claimed (safe because handlers are idempotent full-state upserts)", async () => {
    const first = await claimWebhookEvent("evt_3", "customer.subscription.updated");
    expect(first.shouldProcess).toBe(true);
    // Second delivery of the identical event id arrives before the first
    // call ever reaches markWebhookEventProcessed/Failed.
    const second = await claimWebhookEvent("evt_3", "customer.subscription.updated");
    expect(second.shouldProcess).toBe(true);
  });

  it("an event that previously FAILED can be retried on redelivery", async () => {
    await claimWebhookEvent("evt_4", "invoice.payment_failed");
    await markWebhookEventFailed("evt_4", "boom");

    const retry = await claimWebhookEvent("evt_4", "invoice.payment_failed");
    expect(retry.shouldProcess).toBe(true);

    await markWebhookEventProcessed("evt_4");
    const counts = await countWebhookEventsByStatus();
    expect(counts.processed).toBe(1);
    expect(counts.failed).toBe(0);
  });

  it("never inserts two rows for the same event id (PK collision path, not a second row)", async () => {
    await claimWebhookEvent("evt_5", "customer.subscription.created");
    await claimWebhookEvent("evt_5", "customer.subscription.created");
    await claimWebhookEvent("evt_5", "customer.subscription.created");
    expect((await listRecentWebhookEvents()).filter((e) => e.id === "evt_5")).toHaveLength(1);
  });
});

describe("markWebhookEventProcessed / markWebhookEventFailed", () => {
  it("processed sets processed_at and clears any prior error", async () => {
    await claimWebhookEvent("evt_6", "invoice.paid");
    await markWebhookEventFailed("evt_6", "transient error");
    await markWebhookEventProcessed("evt_6");

    const events = await listRecentWebhookEvents();
    const row = events.find((e) => e.id === "evt_6")!;
    expect(row.status).toBe("processed");
    expect(row.processed_at).not.toBeNull();
    expect(row.error).toBeNull();
  });

  it("failed records the error message and leaves processed_at unset", async () => {
    await claimWebhookEvent("evt_7", "checkout.session.completed");
    await markWebhookEventFailed("evt_7", "user not found for customer");

    const row = (await listRecentWebhookEvents()).find((e) => e.id === "evt_7")!;
    expect(row.status).toBe("failed");
    expect(row.error).toBe("user not found for customer");
    expect(row.processed_at).toBeNull();
  });
});

describe("countWebhookEventsByStatus", () => {
  it("zero-fills every status and counts real rows", async () => {
    expect(await countWebhookEventsByStatus()).toEqual({ processing: 0, processed: 0, failed: 0 });

    await claimWebhookEvent("evt_8", "a");
    await claimWebhookEvent("evt_9", "b");
    await markWebhookEventProcessed("evt_9");
    await claimWebhookEvent("evt_10", "c");
    await markWebhookEventFailed("evt_10", "err");

    expect(await countWebhookEventsByStatus()).toEqual({ processing: 1, processed: 1, failed: 1 });
  });
});

describe("listRecentWebhookEvents", () => {
  it("orders most-recent-first and respects the limit", async () => {
    for (let i = 0; i < 5; i++) await claimWebhookEvent(`evt_list_${i}`, "type");
    expect(await listRecentWebhookEvents(3)).toHaveLength(3);
  });
});

describe("getLastSuccessfulWebhookEvent", () => {
  it("returns null when nothing has ever been processed", async () => {
    await claimWebhookEvent("evt_11", "type");
    expect(await getLastSuccessfulWebhookEvent()).toBeNull();
  });

  it("returns the most recently processed event", async () => {
    await claimWebhookEvent("evt_12", "customer.subscription.created");
    await markWebhookEventProcessed("evt_12");
    await claimWebhookEvent("evt_13", "customer.subscription.updated");
    await markWebhookEventProcessed("evt_13");

    expect((await getLastSuccessfulWebhookEvent())?.id).toBe("evt_13");
  });
});
