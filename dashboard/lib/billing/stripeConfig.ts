/** Milestone 22: Stripe billing environment configuration.
 *
 * Reads exactly the env vars documented in dashboard/STRIPE_TESTING.md.
 * Nothing here ever logs or returns a secret VALUE -- only whether each
 * is present, and (for the secret key) whether it's a live key, which
 * this milestone refuses to use (see BLOCKED_LIVE_KEY_REASON below). */

export interface StripeEnvConfig {
  secretKey: string;
  publishableKey: string | null;
  webhookSecret: string;
  weeklyPriceId: string;
  monthlyPriceId: string;
}

const REQUIRED_VARS = ["STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_WEEKLY_PRICE_ID", "STRIPE_MONTHLY_PRICE_ID"] as const;

export const BLOCKED_LIVE_KEY_REASON =
  "STRIPE_SECRET_KEY is a live key (sk_live_...). Milestone 22 is test-mode only -- real charges are not permitted yet. " +
  "TODO: remove/gate this check in a future milestone when the product is actually ready to go live.";

export type StripeConfigStatus =
  | { configured: true; blocked: false }
  | { configured: false; blocked: false; missing: string[] }
  | { configured: false; blocked: true; reason: string };

function isLiveSecretKey(secretKey: string): boolean {
  return secretKey.startsWith("sk_live_");
}

/** Whether every required Stripe env var is present, and -- the
 * code-level "test mode only" guardrail -- whether the secret key looks
 * like a live key, in which case Stripe is deliberately NOT considered
 * configured (StripeBillingProvider must never initialize with it). */
export function getStripeConfigStatus(): StripeConfigStatus {
  const missing = REQUIRED_VARS.filter((name) => !process.env[name]);
  if (missing.length > 0) {
    return { configured: false, blocked: false, missing: [...missing] };
  }
  const secretKey = process.env.STRIPE_SECRET_KEY!;
  if (isLiveSecretKey(secretKey)) {
    return { configured: false, blocked: true, reason: BLOCKED_LIVE_KEY_REASON };
  }
  return { configured: true, blocked: false };
}

/** Only call once getStripeConfigStatus().configured is true. */
export function getStripeEnvConfig(): StripeEnvConfig {
  return {
    secretKey: process.env.STRIPE_SECRET_KEY!,
    publishableKey: process.env.STRIPE_PUBLISHABLE_KEY || null,
    webhookSecret: process.env.STRIPE_WEBHOOK_SECRET!,
    weeklyPriceId: process.env.STRIPE_WEEKLY_PRICE_ID!,
    monthlyPriceId: process.env.STRIPE_MONTHLY_PRICE_ID!,
  };
}

export type BillingMode = "stripe_test" | "dev" | "unconfigured";

/** Drives the "STRIPE TEST MODE" badge and account/admin billing-mode
 * labels. Never returns a "stripe_live" value -- see getStripeConfigStatus. */
export function getBillingMode(): BillingMode {
  const status = getStripeConfigStatus();
  if (status.configured) return "stripe_test";
  if (process.env.NODE_ENV !== "production") return "dev";
  return "unconfigured";
}
