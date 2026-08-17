import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "@/lib/db/client";
import { getCurrentSubscriptionForUser } from "@/lib/db/subscriptions";
import { createUser, findUserById, markTrialConsumed } from "@/lib/db/users";

import { DevBillingProvider } from "../devBillingProvider";
import type { BillingProvider } from "../types";

const TEST_ORIGIN = "http://localhost:3000";

beforeEach(() => {
  __resetDbForTests();
});

describe("DevBillingProvider.createCheckoutSession", () => {
  it("grants a trialing subscription and marks the trial consumed for a trial-eligible user", async () => {
    const provider = new DevBillingProvider();
    const user = createUser({ email: "eligible@example.com", passwordHash: "h" });

    const result = await provider.createCheckoutSession({ userId: user.id, planId: "weekly", origin: TEST_ORIGIN });
    expect(result).toEqual({ url: "/subscribe/success" });

    const sub = getCurrentSubscriptionForUser(user.id);
    expect(sub?.status).toBe("trialing");
    expect(sub?.trial_ends_at).not.toBeNull();
    expect(findUserById(user.id)?.trial_consumed_at).not.toBeNull();
  });

  it("grants an immediately-active subscription (no trial) for a user who already consumed their trial", async () => {
    const provider = new DevBillingProvider();
    const user = createUser({ email: "consumed@example.com", passwordHash: "h" });
    markTrialConsumed(user.id);

    const result = await provider.createCheckoutSession({ userId: user.id, planId: "monthly", origin: TEST_ORIGIN });
    expect(result).toEqual({ url: "/subscribe/success" });

    const sub = getCurrentSubscriptionForUser(user.id);
    expect(sub?.status).toBe("active");
    expect(sub?.trial_ends_at).toBeNull();
  });

  it("does not grant a second trial when the same user checks out twice (cancel + resubscribe abuse path)", async () => {
    const provider = new DevBillingProvider();
    const user = createUser({ email: "resubscriber@example.com", passwordHash: "h" });

    await provider.createCheckoutSession({ userId: user.id, planId: "weekly", origin: TEST_ORIGIN });
    expect(getCurrentSubscriptionForUser(user.id)?.status).toBe("trialing");
    await provider.cancelSubscription(getCurrentSubscriptionForUser(user.id)!.id);

    await provider.createCheckoutSession({ userId: user.id, planId: "monthly", origin: TEST_ORIGIN }); // switched plans too
    expect(getCurrentSubscriptionForUser(user.id)?.status).toBe("active"); // no second trial
  });

  it("returns an error for an unknown plan id", async () => {
    const provider = new DevBillingProvider();
    const user = createUser({ email: "badplan@example.com", passwordHash: "h" });
    const result = await provider.createCheckoutSession({ userId: user.id, planId: "yearly", origin: TEST_ORIGIN });
    expect(result).toHaveProperty("error");
  });

  it("returns an error for an unknown user id", async () => {
    const provider = new DevBillingProvider();
    const result = await provider.createCheckoutSession({ userId: "no-such-user", planId: "weekly", origin: TEST_ORIGIN });
    expect(result).toHaveProperty("error");
  });
});

describe("DevBillingProvider.createCustomerPortalSession", () => {
  it("always returns null (no hosted portal in dev mode)", async () => {
    const provider: BillingProvider = new DevBillingProvider();
    expect(await provider.createCustomerPortalSession({ userId: "any-user", origin: TEST_ORIGIN })).toBeNull();
  });
});

describe("DevBillingProvider.cancelSubscription", () => {
  it("cancels the given subscription immediately", async () => {
    const provider = new DevBillingProvider();
    const user = createUser({ email: "cancelme@example.com", passwordHash: "h" });
    await provider.createCheckoutSession({ userId: user.id, planId: "weekly", origin: TEST_ORIGIN });
    const sub = getCurrentSubscriptionForUser(user.id)!;

    await provider.cancelSubscription(sub.id);
    expect(getCurrentSubscriptionForUser(user.id)?.status).toBe("canceled");
  });
});

describe("DevBillingProvider.syncSubscription", () => {
  it("returns null since dev-provider subscriptions have no provider_subscription_id to match", async () => {
    const provider = new DevBillingProvider();
    expect(await provider.syncSubscription("sub_not_real")).toBeNull();
  });
});
