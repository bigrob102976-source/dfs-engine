import { describe, expect, it } from "vitest";

import { mapStripeSubscriptionStatus } from "../stripeStatusMapping";

describe("mapStripeSubscriptionStatus", () => {
  it("maps trialing and active directly", () => {
    expect(mapStripeSubscriptionStatus("trialing")).toBe("trialing");
    expect(mapStripeSubscriptionStatus("active")).toBe("active");
  });

  it("maps past_due, unpaid, incomplete, and paused all to past_due", () => {
    expect(mapStripeSubscriptionStatus("past_due")).toBe("past_due");
    expect(mapStripeSubscriptionStatus("unpaid")).toBe("past_due");
    expect(mapStripeSubscriptionStatus("incomplete")).toBe("past_due");
    expect(mapStripeSubscriptionStatus("paused")).toBe("past_due");
  });

  it("maps canceled directly", () => {
    expect(mapStripeSubscriptionStatus("canceled")).toBe("canceled");
  });

  it("maps incomplete_expired to expired", () => {
    expect(mapStripeSubscriptionStatus("incomplete_expired")).toBe("expired");
  });

  it("maps any unrecognized future Stripe status to past_due (no access), never active/trialing", () => {
    // Simulates Stripe's own SDK forward-compatibility OtherString escape hatch.
    expect(mapStripeSubscriptionStatus("some_future_status" as never)).toBe("past_due");
  });
});
